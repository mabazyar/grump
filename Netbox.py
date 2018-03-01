#!/usr/bin/python3

from __future__ import print_function

from pyVmomi import vim

from pyVim.connect import SmartConnectNoSSL, SmartConnect,Disconnect

import requests, json



class Netbox():
    def __init__(self, url, token):
        self.url = url
        self.token = token
        self.header = {'Authorization': 'token {}'.format(self.token)}
        self.__nextURLs = []
    
    def netboxQuery(self, url, HTTPtype, payload = ""):
        if HTTPtype == "get":
            response = requests.get(url, headers=self.header)
        if HTTPtype == "get + payload":
            response = requests.get(url + payload, headers=self.header)
        if HTTPtype == "post":
            response = requests.post(url, json = payload, headers=self.header)
        if HTTPtype == "patch":
            response = requests.patch(url, payload, headers=self.header)
        return response    
    
    def callUrls(self, subUrl):
        self.__nextURLs += [self.url + subUrl]
        nextField = self.netboxQuery(self.__nextURLs[-1], "get").json()['next']
        if nextField == None:
            nextURLs = self.__nextURLs
            self.__nextURLs = []
            return nextURLs
        if not self.url.find("https://"):
            nextField = nextField.replace("http://", "https://")
        self.__nextURLs.append(nextField)
        subUrl = self.__nextURLs[-1].replace(self.url, "")
        return self.callUrls(subUrl)
    
    def apiCall(self, subURL, key):
        if key == "count":
            return self.netboxQuery(self.url + subURL, "get").json()['count']
                
        if key == "results":
            results = []
            URLs =  self.callUrls(subURL)
            for url in URLs:
                results += self.netboxQuery(url, "get").json()['results']
            return results
        
    def getDevices(self, key = ""):
        deviceURL = "/api/dcim/devices/"
        return self.apiCall(deviceURL, key)
        
    def getVirtualMachines(self, key = ""):
        virtualMachinesURL = "/api/virtualization/virtual-machines/"
        return self.apiCall(virtualMachinesURL, key)
    
    def getVirtualMachineID(self, vmName):
        virtualMachineUrl = "/api/virtualization/virtual-machines/?name="
        return self.netboxQuery(self.url + virtualMachineUrl, "get + payload", vmName).json()['results'][0]['id']
    
    def getAllIPs(self):
        ipURL = "/api/ipam/ip-addresses/"
        return self.apiCall(ipURL, "results")
    
    def getVirtualInterfaces(self):
        interfaceURL="/api/virtualization/interfaces"
        return self.apiCall(interfaceURL, "results")
    
    def getIP(self, URL):
        primaryIP= self.netboxQuery(URL, "get").json()['primary_ip']
        
        if primaryIP is not None:
            return primaryIP['address']
        
        return None 
    
    def getSerializedVmInterface(self, virtualMachineName = ""):
        vmInterfaceList = self.getVirtualInterfaces()
        vmInterfaceDict = {}
        for vm in vmInterfaceList:
            interfaceID = vm['id']
            interfaceName = vm['name']
            vmID = vm['virtual_machine']['id']
            vmName = vm['virtual_machine']['name']
            vmMacAddress = vm['mac_address']
            vmDescription = vm['description']
            vmIPaddress = self.getIP(vm['virtual_machine']['url'])
            vmAttribs = {"interfaceID": interfaceID, "interfaceName": interfaceName, 
                         "vmID": vmID, "vmName": vmName, "vmMacAddress": vmMacAddress, 
                         "vmDescription": vmDescription, "vmIPaddress":vmIPaddress}
            if not len(virtualMachineName):
                vmInterfaceDict[vmName] = vmAttribs
            elif vmName == virtualMachineName:
                vmAttribs['vmName'] = vmName
                return vmAttribs
        return vmInterfaceDict  
    
    def getClusterID(self, clusterName):
        clusterUrl = '/api/virtualization/clusters/'
        clusterList = self.apiCall(clusterUrl, "results")
        for cluster in clusterList:
            if cluster['name'] == clusterName:
                return cluster['id']
        return None
        
    def getRoleID(self, roleName):
        roleURL = '/api/dcim/device-roles/'
        roleList = self.apiCall(roleURL, "results")
        for role in roleList:
            if role['name'] == roleName:
                return role['id']
        return None
        
    def getObjectID(self, ObjectName, key):
        if key == "cluster":
            subURL = '/api/virtualization/clusters/'
        elif key == "role":
            subURL = '/api/dcim/device-roles/'
        objectList = self.apiCall(subURL, "results")
        for obj in objectList:
            if obj['name'] == ObjectName:
                return obj['id']
        return None
    
    def addVM(self, vmName, clusterName, roleName, vcpus, memory, disk, hostname = ""):
        vmURL='/api/virtualization/virtual-machines/'
        url = self.url + vmURL
        clusterID = self.getClusterID(clusterName)
        roleID = self.getRoleID(roleName)
        customFields = {"host": hostname}
        payload = {"name":vmName, "cluster": clusterID, "vcpus":vcpus, "memory":memory, 
                  "role":roleID, "disk": disk, "status":0, "custom_fields":customFields}
        return self.netboxQuery(url, "post", payload).text
        
        
        
        
        
        
            
            
            
            
            
        
        
        
    
