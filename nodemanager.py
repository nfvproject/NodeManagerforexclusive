#!/usr/bin/python
#
# Useful information can be found at https://svn.planet-lab.org/wiki/NodeManager
#

# Faiyaz Ahmed <faiyaza at cs dot princeton dot edu>
# Copyright (C) 2008 The Trustees of Princeton University


"""Node Manager"""

import optparse
import time
#import xmlrpclib
#import socket
import os
import sys
#import glob
import pickle
import random
#import resource

import logger
import tools

from config import Config
from plcapi import PLCAPI

from node_config import Node_Config
import commands
class NodeManager:

    PLUGIN_PATH = "/usr/share/NodeManager/plugins"
    DB_FILE = "/var/lib/nodemanager/getslivers.pickle"

    MAP_FILE = "/var/lib/nodemanager/slicemap.pickle"
    
    ROUTER_FILE = "/var/lib/nodemanager/router.pickle"
    VSLIVER_FILE = "/var/lib/nodemanager/vsliver.pickle"
    VIP_FILE = "/var/lib/nodemanager/vip.pickle"
    VMAC_FILE = "/var/lib/nodemanager/vmac.pickle"
    VLANID_FILE = "/var/lib/nodemanager/vlanid.pickle"
    
    PEARL_DEFAULT_CONFIG = "/etc/planetlab/pearl_default_config.xml"
    #PEARL_DPID = 1
    #NODE_ID = 32

    #PEARL_API_URL = "http://192.168.1.40:8080?wsdl"
    #PEARL_DEFAULT_CONFIG = "/etc/planetlab/pearl_default_config.xml"

    # the modules in this directory that need to be run
    # NOTE: modules listed here will also be loaded in this order
    # once loaded, they get re-ordered after their priority (lower comes first)
    # for determining the runtime order
    ###core_modules=['net', 'conf_files', 'slivermanager', 'bwmon']
    #['net', 'conf_files', 'sliverauth', 'vsys_privs', 'rawdisk', 'privatebridge', 
    #'interfaces', 'hostmap', 'sfagids', 'syndicate', 'codemux', 'vsys', 
    #'specialaccounts', 'omf_resctl', 'reservation']
    core_modules=['conf_files']
    
    default_period=600
    default_random=301
    default_priority=100

    def __init__ (self):

        parser = optparse.OptionParser()
        parser.add_option('-d', '--daemon', action='store_true', dest='daemon', default=False,
                          help='run daemonized')
        parser.add_option('-f', '--config', action='store', dest='config', default='/etc/planetlab/plc_config',
                          help='PLC configuration file')
        parser.add_option('-k', '--session', action='store', dest='session', default='/etc/planetlab/session',
                          help='API session key (or file)')
        parser.add_option('-p', '--period', action='store', dest='period', default=NodeManager.default_period,
                          help='Polling interval (sec) - default %d'%NodeManager.default_period)
        parser.add_option('-r', '--random', action='store', dest='random', default=NodeManager.default_random,
                          help='Range for additional random polling interval (sec) -- default %d'%NodeManager.default_random)
        parser.add_option('-v', '--verbose', action='store_true', dest='verbose', default=False,
                          help='more verbose log')
        parser.add_option('-P', '--path', action='store', dest='path', default=NodeManager.PLUGIN_PATH,
                          help='Path to plugins directory')

        # NOTE: BUG the 'help' for this parser.add_option() wont list plugins from the --path argument
        parser.add_option('-m', '--module', action='store', dest='user_module', default='', help='run a single module')
        (self.options, args) = parser.parse_args()

        if len(args) != 0:
            parser.print_help()
            sys.exit(1)

        # determine the modules to be run
        self.modules = NodeManager.core_modules
        node_config = Node_Config()
        self.NODE_TYPE = node_config.NODE_TYPE
        logger.log("node type is %s"%self.NODE_TYPE)

    #wangyang,get slice map from date fetched from myplc
    def getslicemap(self,last_data):
        slicemap = {}
        slivers = []

        try:
            for sliver in last_data['slivers']:
                slices = {}
                if sliver['slice_id'] > 4:
                    logfile = '/var/log/slice/getmap'              
                    logger.logslice("---get slice %s from myplc"%sliver['slice_id'],logfile)
                 #wangyang,what things do we need to focus on , add them here!After this ,we should delete the db file(*.pickle)
                 #wangyang,get vlanid from myplc,vlanid of slivers in one slice should be same 
                 #wangyang,get vip and vmac from myplc,vip and vmac of slivers in one slice should be different,just a global controller can make sure of this. 
                    slices['slice_name'] = sliver['name']
                    slices['slice_id'] = sliver['slice_id']
                    slices['status'] = 'none'
                    slices['port'] = 0
                    slices['keys'] = sliver['keys']
                    slivers.append(slices)                      
                    logger.logslice("---get slice %s successfully,"%slivers,logfile)
            slicemap['slivers'] = slivers
            return slicemap
        except:
            return slicemap

    #wangyang,compare date from myplc and db,update status
    def handlemap(self,slicemap,slicemapdb):
  
        for sliver in slicemap['slivers']:
             isnewslice = 1
             if sliver['slice_id'] > 4:
                 for sliverdb in slicemapdb['slivers']:
                      if sliverdb['slice_id'] == sliver['slice_id']:
                          logger.logslice("keys: %s"%sliver['keys'],'/var/log/slice/key1')
                          logger.logslice("keys: %s"%sliverdb['keys'],'/var/log/slice/key2')
                          if sliverdb['keys'] != sliver['keys']:
                              oldkeys = sliverdb['keys']
                              sliverdb['keys'] = sliver['keys']
                              sliverdb['status'] = 'update'
                              self.rupdatesliver(sliverdb,oldkeys)
                          else:
                              sliverdb['status'] = 'none'    
                          isnewslice = 0
                          break
                 if isnewslice == 1:
                     sliver['status'] = 'new'
                     slicemapdb['slivers'].append(sliver)
                 sliverdb = {}
             sliver = {}
        return slicemapdb

    #wangyang, delete or add or update slivers
    def updatetoRouter(self,slicemapdb,plc): 
        logfile = '/var/log/slice/log'              
        logger.logslice("************************",logfile)
        for sliver in slicemapdb['slivers'][:]:
             if sliver['slice_id'] > 4:
                 if sliver['status'] == 'delete':
                     self.rdeletesliver(sliver)
                     slicemapdb['slivers'].remove(sliver)
                 elif sliver['status'] == 'new':
                     flag = self.rcreatesliver(sliver,plc)
                     if flag == 0:
                         slicemapdb['slivers'].remove(sliver)
                         self.rdeletesliver(sliver)
                         logger.log ("nodemanager: Create this Virtual Router next time")
                 elif sliver['status'] == 'update':
                    #do nothing,this work has been done in function "handlemap()"
                    pass
                 sliver['status'] = 'none'
             sliver = {}
        return slicemapdb
    #wangyang,add,delete,update sliver to router,here just write log    
    def rcreatesliver(self,sliver,plc):

        logger.log ("nodemanager: prepare to create slice,slice is %d - end"%sliver['slice_id'])
        (flag,output)  = commands.getstatusoutput('useradd -m -s /bin/bash -p "%s" %s'%(sliver['slice_name'],sliver['slice_name']))
        #if (flag != 0):
        logger.log ("command output:"%output)
        
        self.rupdatesliver(sliver,oldkeys=[])
        return 1
    def addkeys(self,sliver,keys):
        (flag,output) = commands.getstatusoutput('mkdir /home/%s/.ssh'%sliver['slice_name'])
        logger.log ("command output:"%output)
        (flag,output) = commands.getstatusoutput('touch /home/%s/.ssh/authorized_keys'%sliver['slice_name'])
        logger.log ("command output:"%output)
        (flag,output) = commands.getstatusoutput('chown %s:%s /home/%s/.ssh/authorized_keys'%(sliver['slice_name'],sliver['slice_name'],sliver['slice_name']))
        logger.log ("command output:"%output)
        (flag,output) = commands.getstatusoutput('chmod 600 /home/%s/.ssh/authorized_keys'%sliver['slice_name'])
        logger.log ("command output:"%output)
        for key in keys:
            (flag,output)  = commands.getstatusoutput('echo "%s" >>/home/%s/.ssh/authorized_keys'%(key,sliver['slice_name']))
        logger.log ("command output:"%output)
 
    def rdeletesliver(self,sliver):
        logger.log ("nodemanager: delete slice %s" %(sliver['slice_name']))
        (flag,output)  = commands.getstatusoutput('userdel -fr %s'%sliver['slice_name'])
        logger.log ("command output:"%output)
        #if (flag != 0):
        #    logger.log ("nodemanager: Slice %s delete failed ,not exists"%sliver['slice_name'])
        
    def rupdatesliver(self,sliver,oldkeys):
                #logger.logslice("slicename: %s"%sliver['name'],logfile)    
        #call router API
        # update the user keys to vm
        file = open("/home/%s/.ssh/authorized_keys"%sliver['slice_name'])
        allkeys = []
        for line in file:
            allkeys.append(line)
        otherkeys = [val for val in allkeys if val not in oldkeys]
        addkeys = otherkeys + sliver['keys']
        (flag,output) = commands.getstatusoutput('rm -r /home/%s/.ssh'%sliver['slice_name'])
        logger.log ("command output:"%output)
        self.addkeys(sliver,addkeys)
    def GetSlivers(self, config, plc):
        """Retrieves GetSlivers at PLC and triggers callbacks defined in modules/plugins"""
        
        
        try:
            logger.log("nodemanager: Syncing w/ PLC")
            # retrieve GetSlivers from PLC
            data = plc.GetSlivers()
            # logger.log("call Reportliver")
            #plc.ReportSliverPort({'sliver_port':8765},{'node_id':1,'slice_id':33})
            # use the magic 'default' slice to retrieve system-wide defaults
            self.getPLCDefaults(data, config)
            # tweak the 'vref' attribute from GetSliceFamily
            self.setSliversVref (data)
            # dump it too, so it can be retrieved later in case of comm. failure
            self.dumpSlivers(data)
            # log it for debug purposes, no matter what verbose is
            logger.log_slivers(data)
            logger.verbose("nodemanager: Sync w/ PLC done")
            #last_data=data
            logger.log("*************************************************")
            logger.log("we should provide these information to PEARL TEAM")
            logger.log_map({},"******************************************")
            #wangyang,get slice map from date fetched from myplc
            slicemap = self.getslicemap(data)
            logger.log_map(slicemap,"slicemap")
            #wangyang,get slice map from db
            slicemapdb = self.loadmap(slicemap)
            logger.log_map(slicemapdb,"slicedb")
            #wangyang,compare two files
            slicemapdb = self.handlemap(slicemap,slicemapdb)
            logger.log_map(slicemapdb,"dbafter compare")
            #wangyang,update to router 
            slicemapdb = self.updatetoRouter(slicemapdb,plc)
            logger.log_map(slicemapdb,"db after update")
            #wangyang,update to router
            self.savemap(slicemapdb)
            #wangyang,write into txt
            logger.log_map(slicemapdb,"write to db")
        except:
            logger.log_exc("nodemanager: failed in GetSlivers")
            #  XXX So some modules can at least boostrap.
            logger.log("nodemanager:  Can't contact PLC to GetSlivers().  Continuing.")
            data = {}
            # for modules that request it though the 'persistent_data' property
            #last_data=self.loadSlivers()

        '''
        for sliver in last_data['slivers']:
            logger.log("sliceid is %s"%sliver['slice_id'])
            if sliver['slice_id'] > 4:
                logfile = '/var/log/slice/slice.'+sliver['name']
                #logger.logslice("slicename: %s"%sliver['name'],logfile)    
                logger.logslice("sliceid: %s"%sliver['slice_id'],logfile)
                vmid=self.createslver(sliver['slice_id']) 
                logger.log("vmid is %s"%vmid)
                logger.logmap(sliver['slice_id'],vmid)
                
                #logger.logslice("keys: %s"%sliver['keys'],logfile)
                '''
        logger.log("*************************************************")
        #  Invoke GetSlivers() functions from the callback modules
        for module in self.loaded_modules:
            logger.verbose('nodemanager: triggering %s.GetSlivers'%module.__name__)
            try:
                callback = getattr(module, 'GetSlivers')
                #module_data=data
                #if getattr(module,'persistent_data',False):
                #    module_data=last_data
                callback(data, config, plc)
            except:
                logger.log_exc("nodemanager: GetSlivers failed to run callback for module %r"%module)

    def getPLCDefaults(self, data, config):
        """
        Get PLC wide defaults from _default system slice.  Adds them to config class.
        """
        for slice in data.get('slivers'):
            if slice['name'] == config.PLC_SLICE_PREFIX+"_default":
                attr_dict = {}
                for attr in slice.get('attributes'): attr_dict[attr['tagname']] = attr['value']
                if len(attr_dict):
                    logger.verbose("nodemanager: Found default slice overrides.\n %s" % attr_dict)
                    config.OVERRIDES = attr_dict
                    return
        # NOTE: if an _default slice existed, it would have been found above and
        #           the routine would return.  Thus, if we've gotten here, then no default
        #           slice is bound to this node.
        if 'OVERRIDES' in dir(config): del config.OVERRIDES


    def setSliversVref (self, data):
        """
        Tweak the 'vref' attribute in all slivers based on the 'GetSliceFamily' key
        """
        # GetSlivers exposes the result of GetSliceFamily() as an separate key in data
        # It is safe to override the attributes with this, as this method has the right logic
        for sliver in data.get('slivers'):
            try:
                slicefamily=sliver.get('GetSliceFamily')
                for att in sliver['attributes']:
                    if att['tagname']=='vref':
                        att['value']=slicefamily
                        continue
                sliver['attributes'].append({ 'tagname':'vref','value':slicefamily})
            except:
                logger.log_exc("nodemanager: Could not overwrite 'vref' attribute from 'GetSliceFamily'",name=sliver['name'])

    def dumpSlivers (self, slivers):
        f = open(NodeManager.DB_FILE, "w")
        logger.log ("nodemanager: saving successfully fetched GetSlivers in %s" % NodeManager.DB_FILE)
        pickle.dump(slivers, f)
        f.close()
    #wangyang,save sliver map to db
    def savemap (self, slicemap):
        f = open(NodeManager.MAP_FILE, "w")
        logger.log ("nodemanager: saving successfully fetched slicemap in %s" % NodeManager.MAP_FILE)
        pickle.dump(slicemap, f)
        f.close()
        logger.log_slicemap(slicemap)   
    #def savevlanid (self, vid):
    #    f = open(NodeManager.VLANID_FILE, "w")
    #    logger.log ("nodemanager: saving successfully vlan id in %s" % NodeManager.VLANID_FILE)
    #    pickle.dump(vid, f)
    #    f.close()
    #    logger.log_router(vid,"This is writed to db")
        
    def loadSlivers (self):
        try:
            f = open(NodeManager.DB_FILE, "r+")
            logger.log("nodemanager: restoring latest known GetSlivers from %s" % NodeManager.DB_FILE)
            slivers = pickle.load(f)
            f.close()
            return slivers
        except:
            logger.log("Could not restore GetSlivers from %s" % NodeManager.DB_FILE)
            return {}

    #wangyang,load sliver map from db,otherwise return default config 
    def loadmap (self,slicemap):
        try:
            f = open(NodeManager.MAP_FILE, "r+")
            logger.log("nodemanager: restoring latest known slicemap from %s" % NodeManager.MAP_FILE)
            slicemapdb = pickle.load(f)
            f.close()
            for sliver in slicemapdb['slivers']:
                if sliver['slice_id'] > 4:
                    sliver['status']='delete'
            return slicemapdb
        except:
            logger.log("Could not restore sliver map from %s" % NodeManager.DB_FILE)
            slicemapdb = {}
            slicemapdb['slivers'] = []
            return slicemapdb
    #wangyang,load routerid from db,otherwise return default config        

    '''
    def loadvlanid(self):
        try:
            f = open(NodeManager.VLANID_FILE, "r+")
            logger.log("nodemanager: restoring latest known vlanid from %s" % NodeManager.VLANID_FILE)
            vids = pickle.load(f)
            f.close()
            return vids
        except:
            logger.log("Could not restore vip from %s" % NodeManager.VLANID_FILE)
            vids = []    
            
            for i in range(2000, 4095):
                vid = {}
                vid['vlanid'] = str(i)
                vid['status'] = 'available'
                vids.append(vid)
            return vids
     '''
    def run(self):
        # make sure to create /etc/planetlab/virt so others can read that
        # used e.g. in vsys-scripts's sliceip
        tools.get_node_virt()
        try:
            if self.options.daemon: tools.daemon()

            # set log level
            if (self.options.verbose):
                logger.set_level(logger.LOG_VERBOSE)

            # Load /etc/planetlab/plc_config
            config = Config(self.options.config)

            try:
                other_pid = tools.pid_file()
                if other_pid != None:
                    print """There might be another instance of the node manager running as pid %d.
If this is not the case, please remove the pid file %s. -- exiting""" % (other_pid, tools.PID_FILE)
                    return
            except OSError, err:
                print "Warning while writing PID file:", err

            # load modules
            self.loaded_modules = []
            for module in self.modules:
                try:
                    m = __import__(module)
                    logger.verbose("nodemanager: triggering %s.start"%m.__name__)
                    m.start()
                    self.loaded_modules.append(m)
                except ImportError, err:
                    logger.log_exc ("ERROR while loading module %s - skipping:" % module)
                    # if we fail to load any of these, it's really no need to go on any further
                    if module in NodeManager.core_modules:
                        logger.log("FATAL : failed to load core module %s"%module)
                except AttributeError, err:
                    # triggered when module doesn't have a 'start' method
                    logger.log_exc ("ERROR while starting module %s - skipping:" % module)
                    # if we fail to load any of these, it's really no need to go on any further
                    if module in NodeManager.core_modules:
                        logger.log("FATAL : failed to start core module %s"%module)

            # sort on priority (lower first)
            def sort_module_priority (m1,m2):
                return getattr(m1,'priority',NodeManager.default_priority) - getattr(m2,'priority',NodeManager.default_priority)
            self.loaded_modules.sort(sort_module_priority)

            logger.log('ordered modules:')
            for module in self.loaded_modules:
                logger.log ('%s: %s'%(getattr(module,'priority',NodeManager.default_priority),module.__name__))

            # Load /etc/planetlab/session
            if os.path.exists(self.options.session):
                session = file(self.options.session).read().strip()
            else:
                session = None


            # get random periods
            iperiod=int(self.options.period)
            irandom=int(self.options.random)

            # Initialize XML-RPC client	      
            plc = PLCAPI(config.plc_api_uri, config.cacert, session, timeout=iperiod/2)

            #check auth
            logger.log("nodemanager: Checking Auth.")
            while plc.check_authentication() != True:
                try:
                    plc.update_session()
                    logger.log("nodemanager: Authentication Failure. Retrying")
                except Exception,e:
                    logger.log("nodemanager: Retry Failed. (%r); Waiting.."%e)
                time.sleep(iperiod)
            logger.log("nodemanager: Authentication Succeeded!")
	    plc.__getattr__("GetSlices")

            while True:
            # Main nodemanager Loop
                work_beg=time.time()
                logger.log('nodemanager: mainloop - calling GetSlivers - period=%d random=%d'%(iperiod,irandom))
                self.GetSlivers(config, plc)
                delay=iperiod + random.randrange(0,irandom)
                work_end=time.time()
                work_duration=int(work_end-work_beg)
                logger.log('nodemanager: mainloop has worked for %s s - sleeping for %d s'%(work_duration,delay))
                time.sleep(delay)
        except: logger.log_exc("nodemanager: failed in run")

def run():
    logger.log("======================================== Entering nodemanager.py")
    NodeManager().run()

if __name__ == '__main__':
    run()
else:
    # This is for debugging purposes.  Open a copy of Python and import nodemanager
    tools.as_daemon_thread(run)
