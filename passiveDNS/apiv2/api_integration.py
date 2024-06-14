from fastapi import APIRouter, Depends, HTTPException

import validators

from apiv2.auth import get_current_user
from models.user import User
from models.domain_name import DomainName
from models.ip_address import IPAddress
from models.resolution import Resolution
from models.api_integration import APIIntegration
from analytics.extern_api import (
    ExternAPI,
    VIRUSTOTAL_API,
    ALIENVAULT_API,
    MethodException,
    FormatException,
    RequestException,
)
from db.database import ObjectNotFound

api_integration_router = APIRouter()


def getIPFromResponse(data: str, api: str):
    if api == VIRUSTOTAL_API:
        # virustotal data : {"attributes"{...,"ip_address":..., ...}}
        return data["attributes"]["ip_address"]

    elif api == ALIENVAULT_API:
        # alienvault data : {"address":..., ...}
        return data["address"]


def getDomainFromResponse(data: str, api: str):
    if api == VIRUSTOTAL_API:
        # virustotal data : {"attributes"{...,"host_name":..., ...}}
        return data["attributes"]["host_name"]

    elif api == ALIENVAULT_API:
        # alienvault data : {"hostname":..., ...}
        return data["hostname"]


# get domain resolution from external api
@api_integration_router.post("/apiintegration/dn/{api_name}")
def getDomain(api_name, domain_name: str, user: User = Depends(get_current_user)):
    # check domain exists
    try:
        domain = DomainName.get(domain_name)
    except ObjectNotFound:
        raise HTTPException(
            status_code=404, detail=f"Domain name {domain_name} not found"
        )

    # check api exists
    try:
        api = APIIntegration.get(api_name)
    except ObjectNotFound:
        raise HTTPException(status_code=404, detail="Extern API not found")

    # check user has key for it
    user_key = user.api_keys[api_name]
    if user_key == "":
        raise HTTPException(status_code=404, detail="User key not found")

    # try request
    try:
        response = ExternAPI(api, user_key).requestDomain(domain)
    except FormatException:
        raise HTTPException(status_code=422, detail="The domain is not valid")
    except MethodException as m:
        raise HTTPException(status_code=422, detail=f"The method {m} is not supported")
    except RequestException as r:
        raise HTTPException(status_code=r.status_code, detail=f"Error : {r.message}")

    if api_name == VIRUSTOTAL_API:
        # virustotal response : "data":[...]
        datas = response["data"]

    elif api_name == ALIENVAULT_API:
        # alienvault response : "passive_dns" : [...]
        datas = response["passive_dns"]

    # create new ip and resolution
    count_new = 0
    count_update = 0
    for data in datas:
        ip = getIPFromResponse(data, api_name)
        # check ip is IPv4 format
        if validators.ipv4(ip):
            # check if ip exists in DB
            if IPAddress.exists(ip):
                # check if resolution exists in DB
                if Resolution.exists(domain_name, ip):
                    res_tmp = Resolution.get(domain_name, ip)
                    res_tmp.update(api_name)
                    count_update += 1
                else:
                    res_tmp = Resolution.new(domain_name, ip, api_name)
                    res_tmp.insert()
                    count_new += 1
            else:
                # create ip and resolution
                ip_tmp = IPAddress.new(ip)
                ip_tmp.insert()

                res_tmp = Resolution.new(domain_name, ip, api_name)
                res_tmp.insert()
                count_new += 1

    return {
        "msg": "Domain name resolved",
        "Resolution added": count_new,
        "Resolution updated": count_update,
    }


@api_integration_router.post("/apiintegration/ip/{api_name}")
def getIP(api_name, ip_address: str, user: User = Depends(get_current_user)):
    # check ip exists
    try:
        ip = IPAddress.get(ip_address)
    except ObjectNotFound:
        raise HTTPException(
            status_code=404, detail=f"IP address {ip_address} not found"
        )

    # check api exists
    try:
        api = APIIntegration.get(api_name)
    except ObjectNotFound:
        raise HTTPException(status_code=404, detail="Extern API not found")

    # check user has key for it
    user_key = user.api_keys[api_name]
    if user_key == "":
        raise HTTPException(status_code=404, detail="User key not found")

    # try request
    try:
        response = ExternAPI(api, user_key).requestIP(ip)
    except FormatException:
        raise HTTPException(status_code=422, detail="The ip is not valid")
    except MethodException as m:
        raise HTTPException(status_code=422, detail=f"The method {m} is not supported")
    except RequestException as r:
        raise HTTPException(status_code=r.status_code, detail=f"Error : {r.message}")

    if api_name == VIRUSTOTAL_API:
        # virustotal response : "data":[...]
        datas = response["data"]

    elif api_name == ALIENVAULT_API:
        # alienvault response : "passive_dns" : [...]
        datas = response["passive_dns"]

    # create new domain and resolution
    count_new = 0
    count_update = 0
    for data in datas:
        domain = getDomainFromResponse(data, api_name)
        # check ip is domain format
        if validators.domain(domain):
            # check if domain exists in DB
            if DomainName.exists(domain):
                # check if resolution exists in DB
                if Resolution.exists(domain, ip_address):
                    res_tmp = Resolution.get(domain, ip_address)
                    res_tmp.update(api_name)
                    count_update += 1
                else:
                    res_tmp = Resolution.new(domain, ip_address, api_name)
                    res_tmp.insert()
                    count_new += 1

            else:
                # create domain and resolution
                domain_tmp = DomainName.new(domain)
                domain_tmp.insert()

                res_tmp = Resolution.new(domain, ip_address, api_name)
                res_tmp.insert()
                count_new += 1

    return {
        "msg": "IP address resolved",
        "Resolution added": count_new,
        "Resolution updated": count_update,
    }