import configparser

class CheckWordsPipeline:
    def __init__(self, bad_title_file_path, domain_parking_file_path, maintenance_file_path, flash_file_path):
        config = configparser.ConfigParser()
        config.read('./config.ini')
        wordlists_config = config['wordlists']
        self.bad_title_file_path = wordlists_config['badtitle']
        self.domain_parking_file_path = wordlists_config['domainparking']
        self.maintenance_file_path = wordlists_config['maintainance']
        self.flash_file_path = wordlists_config['flash']
        with open(bad_title_file_path, "r") as f:
            self.bad_title_words = [word.strip() for word in f.readlines()]
        with open(domain_parking_file_path, "r") as f:
            self.domain_parking_words = [word.strip() for word in f.readlines()]
        with open(maintenance_file_path, "r") as f:
            self.maintenance_words = [word.strip() for word in f.readlines()]
        with open(flash_file_path, "r") as f:
            self.flash_words = [word.strip() for word in f.readlines()]

    def process_item(self, item, spider):
        content = item["content"]
        url = item["url"]

        results = {
            "badTitle": self.check_words(self.bad_title_words, item["title"], url, "title"),
            "Domainparking": self.check_words(self.domain_parking_words, content, url, "domainparking"),
            "Maintenance": self.check_words(self.maintenance_words, content, url, "maintenance"),
            "foundFlash": self.check_words(self.flash_words, content, url, "flash"),
        }

    def split_domain(domain):
        if domain.startswith("http://"):
            domain = domain[7:]
        elif domain.startswith("https://"):
            domain = domain[8:]

        # Extract the domain name
        return domain.split("/")[0]
    
    def check_words(self, words, content, url, mode):
        try:
            if mode == "domainparking":
                alfa_target = f'Die Domain "{split_domain(url)}" ist nicht verfügbar.'
                if alfa_target in content:
                    print(f"found: {url} - {mode} - {alfa_target}")
                    return True
                else:
                    for word in words:
                        if word in content:
                            print(f"found: {url} - {mode} - {word}")
                            return True
                    return False
            for word in words:
                if word in content:
                    print(f"found: {url} - {mode} - {word}")
                    return True
            return False
        except TypeError as e:
            pass
