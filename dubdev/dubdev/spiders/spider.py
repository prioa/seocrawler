from pathlib import Path
from scrapy.spidermiddlewares.httperror import HttpError
from twisted.internet.error import DNSLookupError
from twisted.internet.error import TimeoutError
from twisted.internet import ssl
from datetime import datetime
from scrapy import Request
import json
import scrapy
import subprocess
import sys

import dubdev as dub

spider_path = dub.__path__[0] + '/spider.py'

MAX_CMD_LENGTH = 1000

    
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
    name = "dubdev"
    
    def __init__(self, url_list, id_list=None, *args, **kwargs):
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
        ssl_certificate = response.certificate
        ssl_name = ssl_certificate.getSubject()['commonName']
        ssl_expirationDate = ssl_certificate.original.get_notAfter()
        ssl_startDate = ssl_certificate.original.get_notBefore()

        yield {
            'id': response.meta.get('id'),
            'url': response.url,
            'status': response.status,
            'ssl_name': ssl_name.decode() if ssl_name else False,
            'ssl_start': ssl_startDate.decode() if ssl_startDate else False,
            'ssl_expire': ssl_expirationDate.decode() if ssl_expirationDate else False,
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


def crawl(url_list, output_file):

    def is_nested_list(lst):
        for element in lst:
            if isinstance(element, list):
                return True
        return False
    if is_nested_list(url_list):
        temp_url_list = []
        sid_list = []
        for inner_list in url_list:
            temp_url_list.append(inner_list[1])
            sid_list.append(str(inner_list[0]))
        url_list = temp_url_list

    if isinstance(url_list, str):
        url_list = [url_list]
    if isinstance(allowed_domains, str):
        allowed_domains = [allowed_domains]
    if output_file.rsplit('.')[-1] != 'jl':
        raise ValueError("Please make sure your output_file ends with '.jl'.\n"
                         "For example:\n"
                         "{}.jl".format(output_file.rsplit('.', maxsplit=1)[0]))


    command = ['scrapy', 'crawl', spider_path,
               '-a', 'url_list=' + ','.join(url_list),
                '-a', 'follow_links=False',
               '-a', 'sid_list=' + ','.join(sid_list)]
    if len(','.join(url_list)) > MAX_CMD_LENGTH:
        split_urls = _split_long_urllist(url_list)
        split_sids = _split_long_urllist(sid_list)
        for u_list, s_list in zip(split_urls, split_sids):
            command[5] = 'url_list=' + ','.join(u_list)
            command[6] = 'sid_list=' + ','.join(s_list)
            print(command)
            subprocess.run(command)
    else:
        subprocess.run(command)