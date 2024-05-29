from requests import Session


class LoginError(Exception):
    pass


class RequestError(Exception):
    pass


class ApiClient(object):
    def __init__(self, host, username, password):
        self.host = host
        self.username = username
        self.password = password

        self.session = Session()
        self.headers = {}

    def login(self):
        r = self.session.post(
            f"{self.host}/token",
            json={"identity": self.username, "password": self.password},
        )
        if r.status_code != 200:
            raise LoginError(r.status_code)

        jwt = r.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {jwt}"}
        self.session.headers = self.headers

    def dn_update(self, domain_name) -> int:
        r = self.session.put(f"{self.host}/scheduler/dn/{domain_name}")
        return r.status_code

    def dn_list(self):
        r = self.session.get(f"{self.host}/scheduler/alerts")
        if r.status_code != 200:
            raise RequestError(r.status_code)

        return r.json()["dn_list"]
