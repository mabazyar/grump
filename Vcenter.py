#!/usr/bin/python3



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


class Vcenter():
    def __init__(self, host, user, pwd, port):
        self.host = host
        self.user = user
        self.pwd = pwd
        self.port = port
        if hasattr(ssl, '_create_unverified_context'):
            context = ssl._create_unverified_context()
        si = SmartConnect(host = self.host,
                      user = self.user,
                      pwd = self.pwd,
                      port = int(self.port),
                      sslContext = context)
        if not si:
            print("Could not connect to the specified host using specified "
                  "username and password")
            return -1
        self.si = si
        atexit.register(Disconnect, self.si)
        self.content = self.si.RetrieveContent()
        self.children = self.content.rootFolder.childEntity
    def retrieveContent(self):
        return self.content
    def retrieveChildren(self):
        return self.children
    
    
    
    def getNICs(self, summary, guest):
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
    
    
    def diskInfo(self, summary):
        if not hasattr(summary, 'storage'):
            return "0"
        elif not hasattr(summary.storage, "committed"):
            return "0"
        return int(summary.storage.committed / 1024**3)   
    
    def vmsummary(self, summary, guest):
        
        vmsum = {}
        config = summary.config
        net = self.getNICs(summary, guest)
        vmsum['mem'] = str(config.memorySizeMB)
        vmsum['diskGB'] = str(self.diskInfo(summary))
        vmsum['cpu'] = str(config.numCpu)
        vmsum['path'] = config.vmPathName
        vmsum['ostype'] = config.guestFullName
        vmsum['state'] = summary.runtime.powerState
        vmsum['annotation'] = config.annotation if config.annotation else ''
        vmsum['net'] = net
        return vmsum
    
    def retrieveVMs(self):
        for child in self.children:  # Iterate though DataCenters
            dc = child
            clusters = dc.hostFolder.childEntity
            for cluster in clusters:  # Iterate through the clusters in the DC
                #hosts = cluster.host if hasattr(cluster, 'host') else None
                if hasattr(cluster, 'host'):  # Variable to make pep8 compliance
                    hosts = cluster.host
                else:
                    continue
                for host in hosts:  # Iterate through Hosts in the Cluster
                    hostname = host.summary.config.name
                    # Retrieves all the VMs
                    vms = host.vm
                    for vm in vms:  # Iterate through each VM on the host
                        vmname = vm.summary.config.name
                        summary = self.vmsummary(vm.summary, vm.guest)
                        vcpus = summary['cpu']
                        memory = summary['mem']
                        network = summary['net']
                        os = summary['ostype']
                        path = summary['path']
                        annotation = summary['annotation']
                        state = summary['state']
                        disk = summary['diskGB']
                                                
                        vmSerializedData = {"name": vmname, "vcpus": vcpus, "memory": memory, "network": network, "os": os,
                                          "path": path, "comment": annotation, "state": state, "disk": disk, 
                                          "hostname": hostname}
                        yield vmSerializedData
                        
