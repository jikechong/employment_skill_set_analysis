from os import walk
import csv
import sys
import json
import string
import urllib2
from BeautifulSoup import BeautifulSoup
import ConfigParser

LOG_PRODUCTION  = 0
LOG_WARNING     = 1
LOG_ALL_MESSAGE = 10

# LOGLEVEL = LOG_ALL_MESSAGE
LOGLEVEL = LOG_WARNING


class process_request:

    def __init__(self):
        self.load_shml("../../config/whitehouse.cfg")
        self.load_onet_title_lookup("../../model/title_onet.tsv")
        self.load_tree("../../model/")


    def load_shml(self, filename):
        self.CONFIG = ConfigParser.ConfigParser()
        self.CONFIG.read(filename)
        self.SHXML_pshid = self.CONFIG.get("simplyhired_xml_api", "pshid")
        self.SHXML_auth  = self.CONFIG.get("simplyhired_xml_api", "auth" )
        self.SHXML_ssty  = self.CONFIG.get("simplyhired_xml_api", "ssty" )
        self.SHXML_cflg  = self.CONFIG.get("simplyhired_xml_api", "cflg" )


    def load_onet_title_lookup(self, filename):

        # Load Title to ONet lookup
        self.title_onet_lookup = {}

        f = open(filename, "r")
        for line in f:
            tokens = (line.strip()).split("\t")
            if len(tokens) != 2:
                if LOGLEVEL >= LOG_WARNING: 
                    print "WARNING: line \"%s\", %s fields detected, looking for two"%(line,len(tokens))

            title = tokens[0]
            onet  = tokens[1]
        
            self.title_onet_lookup[title] = onet

        f.close()

        if LOGLEVEL >= LOG_ALL_MESSAGE: 
            print "INFO: Check loaded title to ONet lookup"
            print "  %s"%self.title_onet_lookup


    def load_tree(self, filepath):

        # Load trees for all O*Net
        self.trees = {}
        self.clusters = {}
        for (dirpath, dirnames, filenames) in walk(filepath):
            
            # print "INFO: %s"%dirnames

            if len(dirnames) == 0:
                continue

            onet = ""
            if len(dirnames[0]) == 10: 
                onet = dirnames[0]
            else: 
                continue


            # Load tree structure
            try:
                f = open("%s/%s/tree.json"%(filepath,onet), "r")
                j = json.load(f)
                f.close()
            except:
                e = sys.exc_info()[0]
                print "Error: in loading tree.json for %s %s" %(onet, e)
                continue

            self.trees[onet] = j


            # Load cluster meta data
            try:
                f = open("%s/%s/cluster_meta_data.txt"%(filepath,onet), "r")
                reader = csv.reader(f, delimiter='\t')

                self.clusters[onet] = {"clusters":{}, "questions":{}}

                for row in reader:
                    if len(row) != 3:
                        if LOGLEVEL >= LOG_WARNING:
                            print "WARNING: Reading cluster meta data for %s and found %s"%(onet, row)
                        continue

                    self.clusters[onet]["clusters"][row[0]] = {"question":row[1], "query":row[2]}
                    self.clusters[onet]["questions"][row[1]] = {"cluster":row[0], "query":row[2]}
                    
                f.close()
            except:
                e = sys.exc_info()[0]
                print "Error: in loading cluster metadata for %s %s" %(onet,e)
                continue

        
        if LOGLEVEL >= LOG_ALL_MESSAGE:
            print "\nINFO: Check loaded tree json"
            print "  %s"%self.trees
            print "\nINFO: Check loaded cluster meta data"
            print "  %s"%self.clusters



    def process(self, req):

        request = json.loads(req)

        # Look for Title ONets
        keyword = request["keyword"]
        if keyword not in self.title_onet_lookup:
            msg = "ERROR: Keyword not recognized"
            print msg
            return msg
        else:
            onet = self.title_onet_lookup[keyword]
            if LOGLEVEL >= LOG_ALL_MESSAGE:
                print "INFO: %s matched to %s"%(keyword, onet)
        
        # Process location string
        location = request["location"]
        if not location: location = ""
        location_clean = self.clean_string(location)
        if LOGLEVEL >= LOG_ALL_MESSAGE:
            print "INFO: Cleaned location %s"%location_clean        

        context = request["context"]

        # Go through decision tree
        response = self.traverse_response(onet, keyword, location, location_clean, context)
        
        return response



    def traverse_response(self, onet, keyword, location, location_clean, context):
        
        self.yes_list = []
        self.no_list  = []

        if LOGLEVEL >= LOG_ALL_MESSAGE:
            print "INFO: onet %s  keyword %s loation %s  context %s"%(onet,keyword, location_clean, context)

        # Start from root node
        curr_node = '0'

        response = self.traverse_tree(curr_node, onet, keyword, location, location_clean, context)

        return response



    def traverse_tree(self, curr_node, onet, keyword, location, location_clean, context):

        # Check inventory of search results - if less than 10, stop questioning now
        # - Yes/No list implicitly passed as class state
        n_jobs, jobs = self.check_job_market(onet, keyword, location_clean)
        
        if n_jobs < 30:
            response = self.generate_response_in_context(keyword, location, n_jobs=n_jobs, jobs=jobs)
            if LOGLEVEL >= LOG_ALL_MESSAGE:
                print "\nINFO: only %s jobs found, return %s"%(n_jobs,response)
            return response

        curr_cluster = str(self.trees[onet][curr_node]["feature"])
        
        # Check for end of tree
        if curr_cluster == '-2':
            response = self.generate_response_in_context(keyword, location, n_jobs=n_jobs, jobs=jobs)
            if LOGLEVEL >= LOG_ALL_MESSAGE:
                print "\nINFO: Leaf node %s found, return %s"%(curr_node,response)
            return response


        # Otherwise continue recursive tree traversal
        curr_question = self.clusters[onet]['clusters'][curr_cluster]['question']
        curr_keyword  = self.clusters[onet]['clusters'][curr_cluster]['query']

        if LOGLEVEL >= LOG_ALL_MESSAGE:
            print "\nINFO: Traverse Tree at node %s  cluster %s  question %s  keyword %s"%(curr_node, curr_cluster, curr_question, curr_question)

        if not context: context = []

        context_hash = {}
        for ele in context:
            context_hash[ele["question"]] = ele["answer"]

        if curr_question not in context_hash:

            # Ask the question as response
            # - Yes/No list implicitly passed as class state                                                                                                                                             
            response = self.generate_response_in_context(keyword, location, n_jobs=n_jobs, question = curr_question)

            if LOGLEVEL >= LOG_ALL_MESSAGE:
                print "\nINFO: Found next question to ask [%s]"%curr_question
                print "Response: %s"%response

            return response

        curr_choice = context_hash[curr_question]
        
        element = {"choice":curr_choice, "question":curr_question, "query":curr_keyword}
        
        if str(curr_choice) == '1':
            self.yes_list.append(element)
            curr_node = str(self.trees[onet][curr_node]["right_child"])
        elif str(curr_choice) == '0':
            self.no_list.append(element)
            curr_node =str(self.trees[onet][curr_node]["left_child"])
        
        response = self.traverse_tree(curr_node, onet, keyword, location, location_clean, context)        

        return response

    # Check current market place
    def check_job_market(self, onet, keyword, location_clean):
        
        req = 'http://api.simplyhired.com/a/jobs-api/xml-v2/q-'

        # Construct the query
        keyword_clean = self.clean_string(keyword)
        req = req+keyword_clean

        for element in self.yes_list:
            ele_clean = self.clean_string(element["query"])
            req = req+'+AND+'+ele_clean

        for element in self.no_list:
            ele_clean = self.clean_string(element["query"]) 
            req = req+'+AND+NOT+'+ele_clean
        
        req = req+'/l-'+location_clean
        req = req+'?pshid='+self.SHXML_pshid
        req = req+'&ssty='+self.SHXML_ssty
        req = req+'&cflg='+self.SHXML_cflg
        req = req+'&auth='+self.SHXML_auth

        if LOGLEVEL >= LOG_ALL_MESSAGE:
            print "\nINFO: check API with %s"%req 

        response = urllib2.urlopen(req)
        xml = response.read()

        parsed_xml = BeautifulSoup(xml)

        line = str(parsed_xml.shrs.rq.tr)
        line = line.replace('<tr>', "")
        line = line.replace('</tr>', "")
        n_jobs = string.atoi(line)

        jobs = str(parsed_xml.shrs.rs)

        if LOGLEVEL >= LOG_ALL_MESSAGE:
            print "INFO: Total results %s"%n_jobs
        
        return n_jobs,jobs


    
    # Ask the question as response
    def generate_response_in_context(self, keyword, location, n_jobs=-1, question="", jobs=[]):

        # Build Response
        response = {"keyword":keyword, "location":location, "context":[]}
        
        # n_jobs reporting
        if n_jobs != -1:
            response["n_jobs"] = n_jobs

        # Include "Yes" context
        for element in self.yes_list:
            response["context"].append({"question":element["question"], "answer":element["choice"]})

            if str(element["choice"]) != "1":
                print "ERROR: invariant failed in generate_response_in_context for [%s]"%element 
                exit(1)

        # Include "No" context
        for element in self.no_list:
            response["context"].append({"question":element["question"], "answer":element["choice"]})

            if str(element["choice"]) != "0":
                print "ERROR: invariant failed in generate_response_in_context for [%s]"%element 
                exit(1)

        # Include questions
        if len(question) != 0:
            response["question"] = question
            return response
        elif len(jobs) != 0:
            response["jobs"] = jobs
            
            # Todo: Jobs currently in XML format

            return response
        else:
            if len(response["context"]) == 0:
                response["error"] = "No %s jobs in %s found"%(keyword, location)
            else:
                response["error"] = "No %s jobs in %s found with current set of constraints"%(keyword, location)

            return response



    def clean_string(self, input=""):
        output = input.replace(':','%3A')
        output = output.replace(',','%2C')
        output = output.replace(' ','+')
        return output


def main():
    pr = process_request()
    # test = {"keyword": "retail sales","location":"Washington, DC","context": []}
    # test = {"keyword": "retail sales","location":"Washington, DC","context": [{"question":"Can you use devices like scanners?","answer": 1}]}
    test = {"keyword": "retail sales","location":"Modesto, CA","context": [{"question":"Can you use devices like scanners?","answer": 1}]}
    print pr.process(json.dumps(test))



if __name__ == '__main__':
    main()
