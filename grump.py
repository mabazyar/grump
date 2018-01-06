#!/usr/bin/python3
"""
Written by Mohammadali Bazyar
Github: https://github.com/mabazyar
Purpose: Grabs the statistical information available on a vSphere server for each VM and pumps them along to Netbox.

"""
from __future__ import print_function

from pyVmomi import vim

from pyVim.connect import SmartConnectNoSSL, SmartConnect,Disconnect

import argparse
import atexit
import getpass
import json
import ssl
import requests
import configparser


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


def checkArgs():
   args = GetArgs()
   netboxToken=configSectionMap("netbox")['token']
   netboxHeader = {'Authorization': 'token {}'.format(netboxToken)}
   netboxURL= configSectionMap("netbox")['server']

   argDict = {}
   
   if args.config:
      global configFile
      configFile = args.config
   
   
   if args.vcenter:
      host = args.vcenter
   else:
      host = configSectionMap("vcenter")['server']

   
   if args.user:
      user = args.user
   else:
      vcenterUserSuffix = configSectionMap("user")['suffix']
      user = configSectionMap("user")['username'] + vcenterUserSuffix

   
   if args.port:
      port = args.port

   
   if args.password:
      password = args.password
   else:
      password = getpass.getpass(prompt='Enter password for host %s and '
                                        'user %s: ' % (host,user))

   
   argDict = {"password": password, "configFile": configFile, "host": host, "user": user, "port": port}

   return argDict



def GetArgs():
    """
    Supports the command-line arguments listed below.
    """
    parser = argparse.ArgumentParser(
        description='Process args for retrieving all the Virtual Machines')
    parser.add_argument('-v', '--vcenter', required=True, action='store',
                        help='Remote vcenter to connect to')
    parser.add_argument('-o', '--port', type=int, default=443, action='store',
                        help='Port to connect on')
    parser.add_argument('-u', '--user', required=True, action='store',
                        help='User name to use when connecting to host')
    parser.add_argument('-p', '--password', required=False, action='store',
                        help='Password to use when connecting to host')
    parser.add_argument('-c', '--config', required=False, action='store',
                       help='Config file path contains the vcenter and netbox details')
    args = parser.parse_args()
    return args


def getNICs(summary, guest):
    nics = {}
    for nic in guest.net:
        if nic.network:  # Only return adapter backed interfaces
            if nic.ipConfig is not None and nic.ipConfig.ipAddress is not None:
                nics[nic.macAddress] = {}  # Use mac as uniq ID for nic
                nics[nic.macAddress]['netlabel'] = nic.network
                ipconf = nic.ipConfig.ipAddress
                for ip in ipconf:
                    if ":" not in ip.ipAddress:  # Only grab ipv4 addresses
                        nics[nic.macAddress]['ip'] = ip.ipAddress
                        nics[nic.macAddress]['prefix'] = ip.prefixLength
                        nics[nic.macAddress]['connected'] = nic.connected
    return nics

def diskInfo(summary):
  if not hasattr(summary, 'storage'):
    return "0"
  elif not hasattr(summary.storage, "committed"):
    return "0"
  return int(summary.storage.committed / 1024**3)
   

def vmsummary(summary, guest):
    vmsum = {}
    config = summary.config
    net = getNICs(summary, guest)
    vmsum['mem'] = str(config.memorySizeMB)
    #vmsum['diskGB'] = str("%.2f" % (summary.storage.committed / 1024**3))
    vmsum['diskGB'] = str(diskInfo(summary))
    vmsum['cpu'] = str(config.numCpu)
    vmsum['path'] = config.vmPathName
    vmsum['ostype'] = config.guestFullName
    vmsum['state'] = summary.runtime.powerState
    vmsum['annotation'] = config.annotation if config.annotation else ''
    vmsum['net'] = net

    return vmsum


def prepareNetworkComment(netDict):
    netComment = "\n"
    for key in netDict:
        netComment += "-" + key + " ==> {"
        if 'ip' in netDict[key].keys():
            netComment += "IP: " + netDict[key]['ip'] + ", "
        if 'prefix' in netDict[key].keys():
            netComment += "Prefix: " + str(netDict[key]['prefix']) + ", "
        if 'netlabel' in netDict[key].keys():
            netComment += "Netlabel: " + netDict[key]['netlabel']
        netComment += "} \n"
    return netComment

def netboxQuery(type, payload = ""):
    netboxToken=configSectionMap("netbox")['token']
    netboxHeader = {'Authorization': 'token {}'.format(netboxToken)}
    netboxURL= configSectionMap("netbox")['server']
    if type == "get":
      url = netboxURL + '/api/virtualization/clusters/'
      response = requests.get(url, headers=netboxHeader)
      return response
    if type == "post":
      url = netboxURL + "/api/virtualization/virtual-machines/"
      response = requests.post(url, payload, headers=netboxHeader)
    return response



def getNetboxClusterName(dcName, clusterName, hostName):
    if clusterName == hostName:
        return dcName.lower()
    else:
        return dcName.lower() + "-" + clusterName.lower()



def clusterNameIdDict():
  clusterList = netboxQuery("get").json()['results']
  clusterDic = {}
  for cluster in clusterList:
    clusterName = cluster['name']
    clusterID = cluster['id']
    clusterDic[clusterName] = clusterID
  return clusterDic

def netboxify(name, clusterID, vcpus, memory, role, comments, capacity):
    netboxDict = {"name":name, "cluster": clusterID, "vcpus":vcpus, "memory":memory, "role":role, "comments":comments, "disk": capacity}
    return netboxDict

def rectifyNoneType(result):
  if result == None or len(result) == 0:
    return ""
  else:
    return "-" + result

def prepareComment(net, ostype, path, annotation, state, hostname):
    comment = \
    "Network:" + prepareNetworkComment(net) + "\n\n" + \
    "OS Type:\n" + rectifyNoneType(ostype) + "\n\n" + \
    "Hard Disk Path:\n" + rectifyNoneType(path) + "\n\n" + \
    "Host Server:\n" + rectifyNoneType(hostname) + "\n\n" + \
    "State:\n" + rectifyNoneType(state) + "\n\n" + \
    "Annotation:\n" + rectifyNoneType(annotation)
    return comment


def main():
    """
    Iterate through all datacenters and list VM info.
    """
    argDict = checkArgs()

    if hasattr(ssl, '_create_unverified_context'):
      context = ssl._create_unverified_context()
    si = SmartConnect(host=argDict["host"],
                      user=argDict["user"],
                      pwd=argDict["password"],
                      port=int(argDict["port"]),
                      sslContext=context)
    if not si:
        print("Could not connect to the specified host using specified "
              "username and password")
        return -1

    atexit.register(Disconnect, si)

    content = si.RetrieveContent()
    children = content.rootFolder.childEntity
    for child in children:  # Iterate though DataCenters
        dc = child
        clusters = dc.hostFolder.childEntity
        for cluster in clusters:  # Iterate through the clusters in the DC
            hosts = cluster.host  # Variable to make pep8 compliance
            for host in hosts:  # Iterate through Hosts in the Cluster
                hostname = host.summary.config.name
                # Retrieves all the VMs
                vms = host.vm
                for vm in vms:  # Iterate through each VM on the host
                    vmname = vm.summary.config.name
                    summary = vmsummary(vm.summary, vm.guest)
                    vcpus = summary['cpu']
                    memory = summary['mem']
                    comments = prepareComment(summary['net'], summary['ostype'], summary['path'], summary['annotation'], summary['state'], hostname)
                    capacity = summary['diskGB']
                    clusterName = getNetboxClusterName(dc.name, cluster.name, hostname)
                    clusterID = clusterNameIdDict()[clusterName]
                    role = "2"
                    vmData = netboxify(vmname, clusterID, vcpus, memory, role, comments, capacity)
                    print(netboxQuery("post", vmData).text)
                    
# Start program
if __name__ == "__main__":
    main()

