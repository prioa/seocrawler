from pathlib import Path
from scrapy.spidermiddlewares.httperror import HttpError
from twisted.internet.error import DNSLookupError
from twisted.internet.error import TimeoutError
from twisted.internet import ssl
import datetime
from scrapy import Request
import json
import scrapy
import subprocess
import configparser
import platform


import dubdev as dub

spider_path = dub.__path__[0] + '/spider.py'
spider_name = 'dubdev'

config = configparser.ConfigParser()
config.read('./config.ini')


def get_words_from_file(filename):
    with open(filename, 'r') as f:
        words = set(line.strip() for line in f)
        return words
    
def split_domain(domain):
    if domain.startswith("http://"):
        domain = domain[7:]
    elif domain.startswith("https://"):
        domain = domain[8:]

    # Extract the domain name
    return domain.split("/")[0]

def check_words(words, content, domain, mode):
    try:
        if mode == "domainparking":
            alfa_target = 'Die Domain "'  + split_domain(domain) + '" ist nicht verfügbar.'
            if alfa_target in content:
                print(f"found: {domain} - {mode} - {content}")
                return True
        for word in words:
            if word in content:
                print(f"found: {domain} - {mode} - {word}")
                return True
        return False
    except TypeError as e:
        pass


wordlists_config = config['wordlists']
words_flash = get_words_from_file(wordlists_config['flash'])
words_maintainance = get_words_from_file(wordlists_config['maintainance'])
words_domainparking = get_words_from_file(wordlists_config['domainparking'])
words_badtitle = get_words_from_file(wordlists_config['badtitle'])


def get_max_cmd_len():
    system = platform.system()
    cmd_dict = {'Windows': 7000, 'Linux': 100000, 'Darwin': 100000}
    if system in cmd_dict:
        return cmd_dict[system]
    return 6000
MAX_CMD_LENGTH = get_max_cmd_len()

def _split_long_urllist(url_list, max_len=MAX_CMD_LENGTH):
    split_list = [[]]

    for u in url_list:
        temp_len = sum(len(temp_u) for temp_u in split_list[-1])
        if (temp_len < max_len) and (temp_len + len(u) < max_len):
            split_list[-1].append(u)
        else:
            split_list.append([u])
    return split_list


class dubdev(scrapy.Spider):
    name = spider_name
    follow_links = False
    
    def __init__(self, url_list, id_list, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.id_list = json.loads(json.dumps(id_list.split(',')))
        self.start_urls = json.loads(json.dumps(url_list.split(',')))

    def start_requests(self):
        for idx, url in enumerate(self.start_urls):
            try:
                request = Request(url, callback=self.parse, errback=self.errback)
                request.meta['id'] = self.id_list[idx] if idx < len(self.id_list) else None
                yield request
            except Exception as e:
                self.logger.error(repr(e))

    # doing stuff with the response
    def parse(self, response):
        certificate_info = {}
        # SSL
        if response.certificate is not None:
            certificate = response.certificate
            certificate_info['ssl_name'] = certificate.getSubject().get('commonName', False).decode()
            certificate_info['ssl_start'] = certificate.original.get_notAfter().decode()
            certificate_info['ssl_expire'] = certificate.original.get_notAfter().decode()
        else:
            certificate_info['ssl_name'] = False
            certificate_info['ssl_start'] = False
            certificate_info['ssl_expire'] = False

        content = response.xpath('//body//text()').extract()

        yield {
            'id': response.meta.get('id'),
            'url': response.url,
            'status': response.status,
            'title': response.xpath('//title/text()').get(),
            'redirectHTTPS': True if 'https://' in response.url else False,
            'badTitle': check_words(words_badtitle, response.xpath('//title/text()'), response.url, "title"),
            'Domainparking': check_words(words_domainparking, content, response.url, "domainparking"),
            'Maintainance': check_words(words_maintainance, content, response.url, "maintainance"),
            'foundFlash': check_words(words_flash, content, response.url, "flash"),
            'lastModified': response.headers.to_unicode_dict().get('last-modified'),
            'tableLayout': True if len(response.xpath('//div')) <= len(response.xpath('//tr')) else False, # add check here for download sites
            **certificate_info
        }



    def errback(self, failure):
        if not failure.check(scrapy.exceptions.IgnoreRequest):
            self.logger.error(repr(failure))
            yield {'id': failure.request.meta.get('id'),
                    'url': failure.request.url,
                   'crawl_time': datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                   'errors': repr(failure)}
        if failure.check(DNSLookupError):
            f_dns = open("dnsErrors.txt", "a")
            request = failure.request
            f_dns.write(f"{failure.request.meta.get('id')}, {failure.request.url}\n")
            self.logger.error('ATTENTION: DNSLookupError on %s', request.url)
            yield {'id': failure.request.meta.get('id'),
                    'url': failure.request.url,
                    'crawl_time': datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                    'errors': repr(failure)}
            f_dns.close()
        elif failure.check(HttpError):
            f_http = open("httpErrors.txt", "a")
            response = failure.value.response
            f_http.write(f"{failure.request.meta.get('id')}, {failure.request.url}\n")
            self.logger.error('HttpError on %s', response.url)
            f_http.close()
        elif failure.check(TimeoutError):
            f_timeout = open("timeoutErrors.txt", "a")
            request = failure.request
            f_timeout.write(f"{failure.request.meta.get('id')}, {failure.request.url}\n")
            self.logger.error('TimeoutError on %s', request.url)
            f_timeout.close()




def crawl(url_list, output_file, follow_links=False):

    def is_nested_list(lst):
        for element in lst:
            if isinstance(element, list):
                return True
        return False
    if is_nested_list(url_list):
        temp_url_list = []
        id_list = []
        for inner_list in url_list:
            temp_url_list.append(inner_list[1])
            id_list.append(str(inner_list[0]))
        url_list = temp_url_list

    if isinstance(url_list, str):
        url_list = [url_list]

    if output_file.rsplit('.')[-1] != 'jl':
        raise ValueError("Please make sure your output_file ends with '.jl'.\n"
                         "For example:\n"
                         "{}.jl".format(output_file.rsplit('.', maxsplit=1)[0]))

    command = ['scrapy', 'crawl', 'dubdev',
               '-a', 'url_list=' + ','.join(url_list),
               '-a', 'id_list=' + ','.join(id_list),
               '-a', 'follow_links=' + str(follow_links),
               '-s', 'DOWNLOAD_TIMEOUT=' + config['general']['download_timeout'],
               '-s', 'RETRY_TIMES=' + config['general']['retries'],
               '-s', 'LOG_FILE=test.log',
               '-o', output_file]
    if len(','.join(url_list)) > MAX_CMD_LENGTH:
        split_urls = _split_long_urllist(url_list)
        split_sids = _split_long_urllist(id_list)
        for u_list, s_list in zip(split_urls, split_sids):
            command[4] = 'url_list=' + ','.join(u_list)
            command[5] = 'id_list=' + ','.join(s_list)
            subprocess.run(command)
    else:
        subprocess.run(command)