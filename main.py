from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from bulkseospider.spiders.spider import crawl
from tqdm import tqdm
import jsonlines

import pandas as pd


import configparser
import datetime
import time

start_time = time.time()


timestamp = datetime.datetime.now()
formatted_timestamp = timestamp.strftime("%Y%m%d_%H%M%S")



config = configparser.ConfigParser()
config.read('config.ini')

 
project_config = config['project']
general_config = config['general']
wordlists_config = config['wordlists']


def get_domains(start, end):
    df = pd.read_csv(project_config['file_name'], sep=project_config['seperator'])
    id_col_name = project_config['id_column_name']
    domain_col_name = project_config['domain_column_name']
    df = df[[id_col_name, domain_col_name]]
    df = df[start:end]
    crawl_limit = int(project_config['crawl_limit'])
    if crawl_limit != 0:
        df[:crawl_limit]
    df_lst = df.values.tolist()
    return df_lst


def get_words_from_file(filename):
    try:
        with open(filename, 'r') as f:
            words = set(line.strip() for line in f)
        return words
    except:
        print(f"{filename} not found")
        exit(3)

if __name__ == '__main__':
    print("██████╗░██╗░░░██╗██╗░░░░░██╗░░██╗  ░██████╗███████╗░█████╗░\n██╔══██╗██║░░░██║██║░░░░░██║░██╔╝  ██╔════╝██╔════╝██╔══██╗\n██████╦╝██║░░░██║██║░░░░░█████═╝░  ╚█████╗░█████╗░░██║░░██║\n██╔══██╗██║░░░██║██║░░░░░██╔═██╗░  ░╚═══██╗██╔══╝░░██║░░██║\n██████╦╝╚██████╔╝███████╗██║░╚██╗  ██████╔╝███████╗╚█████╔╝\n╚═════╝░░╚═════╝░╚══════╝╚═╝░░╚═╝  ╚═════╝░╚══════╝░╚════╝░\n░█████╗░██████╗░░█████╗░░██╗░░░░░░░██╗██╗░░░░░███████╗██████╗░\n██╔══██╗██╔══██╗██╔══██╗░██║░░██╗░░██║██║░░░░░██╔════╝██╔══██╗\n██║░░╚═╝██████╔╝███████║░╚██╗████╗██╔╝██║░░░░░█████╗░░██████╔╝\n██║░░██╗██╔══██╗██╔══██║░░████╔═████║░██║░░░░░██╔══╝░░██╔══██╗\n╚█████╔╝██║░░██║██║░░██║░░╚██╔╝░╚██╔╝░███████╗███████╗██║░░██║\n░╚════╝░╚═╝░░╚═╝╚═╝░░╚═╝░░░╚═╝░░░╚═╝░░╚══════╝╚══════╝╚═╝░░╚═╝")
    for key in wordlists_config:
        globals()['words_' + key] = get_words_from_file(wordlists_config[key])
    chunk_size = int(general_config['chunk_size'])
    df_length = len(pd.read_csv(project_config['file_name'], sep=project_config['seperator']))
    output_file = project_config['name'] + f"_results_{str(formatted_timestamp)}.jl"
    for i in range(0, df_length, chunk_size):
        domains = get_domains(i, i + chunk_size)
        crawl(domains, output_file)
    
    print(f"Crawler finished in {time.time() - start_time:.2f} seconds")
    counter_nores = 0
    counter_full = 0
    with jsonlines.open(output_file) as reader:
        for obj in reader:
            counter_full += 1
            if ('generator' in obj and obj['generator'] != "None") and \
            ('cms' in obj and obj['cms'] == "None"):
                counter_nores += 1
                print(obj['url'])
    print(f"found {counter_full} items.\n{counter_nores} items without error")
