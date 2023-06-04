from scrapy.spidermiddlewares.httperror import HttpError
from twisted.internet.error import DNSLookupError
from twisted.internet.error import TimeoutError
import datetime
from scrapy import Request
import json
import scrapy
import subprocess
import configparser
import platform
import pandas as pd
import phonenumbers
from phonenumbers.phonenumberutil import NumberParseException

import validators
import re
from fuzzywuzzy import fuzz

import bulkseospider as bss

spider_path = bss.__path__[0] + '/spider.py'
spider_name = 'bulkseospider'

config = configparser.ConfigParser()
config.read('./config.ini')
wordlists_config = config['wordlists']
project_config = config['project']


def get_phone_numbers(content):
    phone_numbers = []
    for a in content:
        try:
            number = phonenumbers.parse(a, project_config['country_code'])
            number = phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
        except NumberParseException as e:
            number = a
        if number:
            if number not in phone_numbers:
                phone_numbers.append(number)
            
    return ", ".join(phone_numbers)

def get_email(content):
    emails = []
    for a in content:
            if validators.email(a):
                if a not in emails:
                  emails.append(a)
    return ", ".join(emails)


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

def find_duplicates(lst):
    return len(lst) != len(set(lst))

def check_words(words, content, domain, mode):
    try:
        if mode == "domainparking":
            alfa_target = 'Die Domain "'  + split_domain(domain) + '" ist nicht verfügbar.'
            if alfa_target in content:
                return True
            else:
                for word in words:
                    if word in content:
                        return True
                return False
        for word in words:
            if word in content:
                return True
        return False
    except TypeError as e:
        pass

words_flash = get_words_from_file(wordlists_config['flash'])
words_maintainance = get_words_from_file(wordlists_config['maintainance'])
words_domainparking = get_words_from_file(wordlists_config['domainparking'])
words_badtitle = get_words_from_file(wordlists_config['badtitle'])

def check_social(content, target):
    if target in str(content):
        return True
    return False

def check_cms(content):
    df = pd.read_csv(wordlists_config['cms'], delimiter=';')
    for index, row in df.iterrows():
        #print(row['location'])
        if row['location'] == "href":
            targets = content.xpath('//@href').getall()
            if row['search_string'] in str(targets):
                return row['cms']
        if row['location'] == "script" or row['location'] == "img":
            targets = content.xpath('//@src').getall()
            if row['search_string'] in str(targets):
                return row['cms']
        if row['location'] == "html":
            if row['search_string'] in str(content.body.decode('utf-8', errors="replace")):
                return row['cms']
        if row['location'] == "meta":
            targets = content.xpath('//meta/@content').getall()
            if row['search_string'] in str(targets):
                return row['cms']
    return False

def check_shop(content):
    df = pd.read_csv(wordlists_config['shop'], delimiter=';')
    for index, row in df.iterrows():
        #print(row['location'])
        if row['location'] == "href":
            targets = content.xpath('//@href').getall()
            if row['search_string'] in str(targets):
                return row['shop']
        if row['location'] == "script" or row['location'] == "img":
            targets = content.xpath('//@src').getall()
            if row['search_string'] in str(targets):
                return row['shop']
        if row['location'] == "html":
            if row['search_string'] in str(content.body.decode('utf-8', errors="replace")):
                return row['shop']
        if row['location'] == "meta":
            targets = content.xpath('//meta/@content').getall()
            if row['search_string'] in str(targets):
                return row['shop']
    return False

def check_page(content, targets):
    for target in targets:
        if target.lower() in str(content).lower():
            return True
    return False

def check_wp_version(generator_tag):
    try:
        if "WordPress" in str(generator_tag):
            return str(generator_tag).split()[1]
    except:
        return None


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


class bulkseospider(scrapy.Spider):
    name = spider_name
    follow_links = False
    
    def __init__(self, url_list, id_list, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.id_list = json.loads(json.dumps(id_list.split(',')))
        self.start_urls = json.loads(json.dumps(url_list.split(',')))

    def start_requests(self):
        for idx, url in enumerate(self.start_urls):
            try:
                url = 'http://' + url
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

        # Phone
        hrefs = response.css("a::attr(href)").getall()
        hrefs_complete = response.css("a").getall()
        tel_hrefs = [href.split(":")[1] for href in hrefs if href.startswith("tel:")]
        mail_hrefs = [href.split(":")[1] for href in hrefs if href.startswith("mailto:")]

        # legal lists
        imprint_list = ['Impressum', 'Imprint', 'Legal Notice', 'Legal Disclosure', 'Site Notice', 'Anbieterkennzeichnung', 'Offenlegung nach § 5 TMG', 'Angaben gemäß § 5 Abs. 1 E-Commerce-Gesetz (ECG)', 'Anbieterinformationen']
        legal_list = ['Datenschutz', 'Datenschutzerklärung', 'Datenschutzrichtlinie', 'Datenschutzhinweise', 'Datenschutzbestimmungen', 'Privacy Policy', 'Privacy Statement', 'Data Protection Policy', 'Datenschutzinformationen', 'Datenschutzregeln', 'Datenschutzbelehrung']


        content = response.body.decode('utf-8', errors="replace")

        BODY_TEXT_SELECTOR = '//body//span//text() | //body//p//text() | //body//li//text()'
        body_text = ' '.join(response.xpath(BODY_TEXT_SELECTOR).extract())
        cleaned_text = re.sub(r'[^\w\s]', '', body_text)
        words = cleaned_text.split()

        h1 = response.xpath('//h1/text()').get()
        h2 = response.xpath('//h2/text()').getall()
        title = response.xpath('//title/text()').get()
        description = response.xpath("//meta[@name='description']/@content")

        yield {
            'id': response.meta.get('id'),
            'url': response.url,
            'status': response.status,
            'title': title.strip() if title else 0,
            'redirectHTTPS': True if 'https://' in response.url else False,
            'badTitle': check_words(words_badtitle, response.xpath('//title/text()'), response.url, "title"),
            'Domainparking': check_words(words_domainparking, content, response.url, "domainparking"),
            'Maintainance': check_words(words_maintainance, content, response.url, "maintainance"),
            'foundFlash': check_words(words_flash, content, response.url, "flash"),
            'lastModified': response.headers.to_unicode_dict().get('last-modified'),
            'tableLayout': len(response.xpath('//tr')) != 0 and len(response.xpath('//div')) <= len(response.xpath('//tr')),
            'smFacebook': check_social(hrefs, "https://www.facebook.com/"),
            'smInstagram': check_social(hrefs, "https://www.instagram.com/"),
            'smTwitter': check_social(hrefs, "https://www.twitter.com/"),
            'smYoutube': check_social(hrefs, "https://www.youtube.com/channel"),
            'smLinkedin': check_social(hrefs, "https://www.linkedin.com/company/"),
            'smXing': check_social(hrefs, "https://www.xing.com/pages/"),
            'smPinterest': check_social(hrefs, "https://www.pinterest.at/"),
            'generator': str(response.xpath("//meta[@name='generator']/@content").get()),
            'cms': check_cms(response),
            'shop': check_shop(response),
            'cmsVersion': check_wp_version(str(response.xpath("//meta[@name='generator']/@content").get())),
            'phone': get_phone_numbers(tel_hrefs),
            'email': get_email(mail_hrefs),
            'impressum': check_page(hrefs_complete, imprint_list),
            'datenschutz': check_page(hrefs_complete, legal_list),
            "H1": len(response.xpath('//h1').getall()),
            "H1Size": len(h1) if len(response.xpath('//h1').getall()) == 1 and h1 else "NaN",
            "H1inBody": fuzz.token_set_ratio(h1, body_text) if h1 and body_text else 0,
            "H1inTitle": fuzz.token_set_ratio(h1, title.strip()) if h1 and title else 0,
            "H1inMeta": fuzz.token_set_ratio(h1, description.extract_first().strip()) if h1 and description else 0,
            "SEOScore": fuzz.token_set_ratio(h1, body_text, description.extract_first().strip(), title.strip()) if h1 and body_text and description and title else 0,
            "MetaDescriptionSize": len(description.extract_first().strip()) if description else 0,
            "H2": len(response.xpath('//h2').getall()),
            "UniqueH2Tags": 'False' if find_duplicates(h2) else 'True',
            "TitleTagSize": len(title.strip()) if title else 0,
            "WordCount": len(words),
            "Viewport": 'True' if response.xpath("//meta[@name='viewport']").get() is not None else 'False',
            **certificate_info,
            'crawl_time': datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
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

    command = ['scrapy', 'crawl', 'bulkseospider',
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