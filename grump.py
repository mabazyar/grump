#!/usr/bin/python3

import requests, json, sys, getpass, configparser

configFile="./grump.conf"
config = configparser.ConfigParser()
config.read(configFile)

def configSectionMap(section):
    serializedSection = {}
    options = config.options(section)
    for option in options:
        try:
            serializedSection[option] = config.get(section, option)
            if serializedSection[option] == -1:
                DebugPrint("skip: %s" % option)
        except:
            print("exception on %s!" % option)
            serializedSection[option] = None
    return serializedSection

netboxToken=configSectionMap("netbox")['token']
netboxHeader = {'Authorization': 'token {}'.format(netboxToken)}
netboxURL= configSectionMap("netbox")['server']

vcenterURL = configSectionMap("vcenter")['server']
vcenterUserSuffix = configSectionMap("user")['suffix']

s = requests.Session()


def getUserPass():
  username = configSectionMap("user")['username'] + vcenterUserSuffix
  
  try:
    password = getpass.getpass()
  except Exception as error:
    print('ERROR', error)
  
  authKey = {'username': username, 'password': password}
  return authKey

def getAuthenticated():
  authPair = getUserPass()
  username = authPair['username']
  password = authPair['password']

  s.auth = (username, password)
  s.post(vcenterURL + '/rest/com/vmware/cis/session')

def rawJsonHosts():
  return(s.get(vcenterURL + '/rest/vcenter/host').json())


def getCluster(host):
  hostname = host.split(".")[0]
  hostnameList = hostname.split("-")
  if len(hostnameList) > 3:
    cluster = hostnameList[-1]
  else:
    cluster = hostnameList[2]
  return cluster

def listHostsAndClusters():
  dictList = rawJsonHosts()['value']
  hostAndClusterList = []
  for dict in dictList:
    hostAndClusterList += [{"hostid": dict["host"], "cluster": getCluster(dict["name"]), "name": dict["name"]}]
  return hostAndClusterList

def listVMsInHost(host):
  URL = vcenterURL + "/rest/vcenter/vm?filter.hosts=" + host
  return s.get(URL).json()

def netboxGetQuery(url):
  response = requests.get(url, headers=netboxHeader)
  return response

def feedNetboxVM(vmData):
  virtualizationURL = netboxURL + "/api/virtualization/virtual-machines/"
  response = requests.post(virtualizationURL, vmData, headers=netboxHeader)
  print(response.text)



def getClusterID():
  clusterUrl = netboxURL + '/api/virtualization/clusters/'
  clusterList = netboxGetQuery(clusterUrl).json()['results']

  clusterDic = {}
  for cluster in clusterList:
    clusterName = cluster['name']
    clusterID = cluster['id']
    clusterDic[clusterName] = clusterID
  return clusterDic

def getDiskID(vmID):
  URL = vcenterURL + "/rest/vcenter/vm/" + vmID + "/hardware/disk"
  diskList = s.get(URL).json().get('value', None) 
  if type(diskList) == list:
    print(diskList[0])
    diskID = diskList[0].get('disk', None)
    return diskID
  else:
    return ""

def getDiskCapacity(vmID):
  diskID = getDiskID(vmID)
  URL = vcenterURL + "/rest/vcenter/vm/" + vmID + "/hardware/disk/" + diskID
  vmDiskDetails = s.get(URL).json()['value']
  capacity2GB = str(int(int(vmDiskDetails.get('capacity',0))/1073741824))
  return capacity2GB

def netboxify(hostid, cluster, hostname):
  clusterDic = getClusterID()
  for vm in listVMsInHost(hostid)['value']:
    print(vm)
    vmID = vm.get('vm', None)
    name = vm.get('name', None) 
    vcpus = vm.get('cpu_count', None) 
    memory = vm.get('memory_size_MiB', None) 
    clusterID = clusterDic[cluster]
    role = 2
    capacity = getDiskCapacity(vmID)
    comments = "vmID:" + vm['vm'] + " hostID:" + hostid + " Host:" + hostname
    netboxDict = {"name":name, "cluster": clusterID, "vcpus":vcpus, "memory":memory, "role":role, "comments":comments, "disk": capacity}
    feedNetboxVM(netboxDict)
    
  

def listVMsAndFeedNetbox():
  for hostClusterPair in listHostsAndClusters():
    hostid = hostClusterPair['hostid']
    cluster = hostClusterPair['cluster']
    hostname = hostClusterPair['name']
    netboxify(hostid, cluster, hostname)
  
getAuthenticated()
listVMsAndFeedNetbox()

