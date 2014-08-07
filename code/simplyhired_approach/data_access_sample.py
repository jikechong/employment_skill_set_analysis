import os
import csv

class skill_extraction:
    
    def __init__(self, config_file):

        # Read configuration file 
        self.data_filename = "../../data/job_sample_1000.txt"



    def read_jobs(self):
        '''
        Reading job information from data file
        '''
        
        jobs = []

        with open(self.data_filename, 'rU') as f:
            reader = csv.reader(f, delimiter='\t', quoting=csv.QUOTE_MINIMAL)
            # headers = reader.next()
            # headers.append("skills")

            for row in reader:

                skills = self.extract_one_job_skills(row[7])

                print row[0]
                print "  %s\n"%(skills)
        
                jobs.append({"title":row[0],"row":row,"skills":skills})

        return jobs



    def extract_one_job_skills(self, line):
        '''
        Your skills extractor in this function
        '''

        return "skills"



    def dump_results(self, jobs, out_filename):
        '''
        Dump results to file
        '''
        with open(out_filename, 'w') as f:
            writer = csv.writer(f, delimiter='\t', quoting=csv.QUOTE_MINIMAL)
            #writer.writerow(self.headers)

            for job in jobs:
                row = job["row"]
                row.append(job["skills"])
                writer.writerow(row)
        
        



def main():
    
    se = skill_extraction("../../config/skill_extraction.cfg")

    jobs = se.read_jobs()
    print "\nCompleted parsing %s jobs."%(len(jobs))

    os.system("mkdir -p ../../var")
    se.dump_results(jobs, "../../var/output.txt")
    print "\nWrote results out to file.\n"


if __name__ == '__main__':
    main()    
