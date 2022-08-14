from datetime import datetime
from operator import attrgetter

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.base.app_manager import lookup_service_brick
from ryu.controller.handler import MAIN_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import CONFIG_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.topology import event, switches
from ryu.ofproto.ether import ETH_TYPE_IP
from ryu.topology.api import get_switch, get_link
from ryu.ofproto import ofproto_v1_3
from ryu.lib import hub
from ryu.lib.packet import packet
from ryu.lib.packet import arp

import time
import random
import simple_awareness
import simple_delay
import main
import pandas as pd
import json, ast
import setting
import csv
import time
import numpy as np

path = '/home/imperatrice/Documents/RSIR-Reinforcement-Learning-and-SDN-Intelligent-Routing/SDNapps_proac/' 
pathAM = '/home/imperatrice/Documents/RSIR-Reinforcement-Learning-and-SDN-Intelligent-Routing/SDNapps_proac/Month2/' 

class simple_Monitor(app_manager.RyuApp):
    """simple_awarenesssimple_awareness

        A Ryu app for netowrk monitoring. It retreieves statistics information through openflow
        of datapaths at the Data Plane.
        
        This class contains functions belonging to the Statistics module and Flow Installation module
        of the Control Plane.
        
        I also contains the functions corresponding to the Process Statistics module of the
        Management Plane in order to adventage the monitorin threading for statistics processing.
    """

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION] # overflow verson 
    
    _CONTEXTS = {"simple_awareness": simple_awareness.simple_Awareness,
                 "simple_delay": simple_delay.simple_Delay}

    def __init__(self, *args, **kwargs):
        super(simple_Monitor, self).__init__(*args, **kwargs)
        
        self.name = "monitor"
        self.count_monitor = 0
        self.topology_api_app = self
        self.start_timestamp = datetime.now()
        self.datapaths = {}
        self.port_stats = {}
        self.port_speed = {}
        self.flow_stats = {}
        self.flow_speed = {}
        self.flow_loss = {}
        self.port_loss = {}
        self.link_loss = {}
        self.net_info = {}
        self.net_metrics= {}
        self.link_free_bw = {}
        self.link_used_bw = {}
        self.stats = {}
        self.port_features = {}
        self.free_bandwidth = {}
        self.awareness = kwargs["simple_awareness"]
        self.delay = kwargs["simple_delay"]
        self.paths = {}
        self.installed_paths = {}
        self.amcounter = 0
        self.monitor_thread = hub.spawn(self.monitor)
        self.aggregate_adj_matrix = [[0 for i in range(23)] for i in range(23)]
        self.traffic_adj_matrix = [[0 for i in range(23)] for i in range(23)]
        

    @set_ev_cls(ofp_event.EventOFPStateChange,
                [MAIN_DISPATCHER, DEAD_DISPATCHER])

    def state_change_handler(self, ev):
        """
            Record datapath information.
        """
        datapath = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            if datapath.id not in self.datapaths:
                self.logger.debug('Datapath registered: %016x', datapath.id)
                print ('Datapath registered:', datapath.id) ##
                self.datapaths[datapath.id] = datapath
        elif ev.state == DEAD_DISPATCHER:
            if datapath.id in self.datapaths:
                self.logger.debug('Datapath unregistered: %016x', datapath.id)
                print ('Datapath unregistered:', datapath.id)
                del self.datapaths[datapath.id] # A corriger pour le temps normal !!!!!!!

    def monitor(self): 
        """
            Main entry method of monitoring traffic.
        """
        while True:
            self.count_monitor += 1
            self.stats['flow'] = {}
            self.stats['port'] = {}
            print("[Statistics Module Ok]")
            print("[{0}]".format(self.count_monitor)) # each cycle print [1] ---- 
            
            for dp in self.datapaths.values():
                self.port_features.setdefault(dp.id, {})
                self.paths = None
                self.request_stats(dp)
       
            if sum(map(sum, self.aggregate_adj_matrix)) == 0:
                # if this is the first traffic file:
                self.aggregate_adj_matrix = self.traffic_adj_matrix
                pd.DataFrame(np.array(self.traffic_adj_matrix)).to_csv(pathAM +str(self.count_monitor) + "adj.csv")
                #pd.DataFrame(np.array(self.aggregate_adj_matrix)).to_csv(pathAM +str(self.count_monitor) + "adj_aggregate.csv")
                self.traffic_adj_matrix = [[0 for i in range(23)] for i in range(23)]
                
            else:
                # Calculate the difference between previous aggregate and current traffice:
                diff_matrix = [[0 for i in range(23)] for i in range(23)]
                for r in range(23):
                    for c in range(23):
                        curr_period_traffic = self.traffic_adj_matrix[r][c] - self.aggregate_adj_matrix[r][c]
                        if curr_period_traffic <= 0:
                            diff_matrix[r][c] = 0
                        else:
                            diff_matrix[r][c] = curr_period_traffic
                self.aggregate_adj_matrix = self.traffic_adj_matrix
                self.traffic_adj_matrix = [[0 for i in range(23)] for i in range(23)]
                time_since_last_monitor = (datetime.now() - self.start_timestamp).total_seconds()
                self.start_timestamp = datetime.now()
                print("Time since last monitor: ", time_since_last_monitor)
                pd.DataFrame(np.array(diff_matrix)).to_csv(pathAM + str(self.count_monitor) +"_" + str(time_since_last_monitor)+ "_adj.csv")
                
                #pd.DataFrame(np.array(self.aggregate_adj_matrix)).to_csv(pathAM +str(self.count_monitor) + "adj_aggregate.csv")
                #print("aggregated matrix: ",self.aggregate_adj_matrix)
                #print("current matrix: ",diff_matrix)
            
            #write to file
            if self.awareness.link_to_port:
                # tensordecomposition function that calculates the path 
                self.flow_install_monitor() # control plane (flow installation module)
            if self.stats['port']:
                self.get_port_loss()
                self.get_link_free_bw()
                self.get_link_used_bw()
                self.write_values()

            hub.sleep(setting.MONITOR_PERIOD)
            if self.stats['port']:
                self.show_stat('link')
                hub.sleep(1)

#---------------------CONTROL PLANE FUNCTIONS----------------------------------------
#---------------------FLOW INSTALLATION MODULE FUNCTIONS ----------------------------

    def flow_install_monitor(self):
        #installs the paths for each src-dst pairs 
        #how ? 
        print("[Flow Installation Ok]")
        out_time= time.time()
        for dp in self.datapaths.values():
            for dp2 in self.datapaths.values():
                if dp.id != dp2.id:
                    ip_src = '10.0.0.'+str(dp.id)
                    ip_dst = '10.0.0.'+str(dp2.id)
                    # what is dp.id , dp2.id ? 
                    self.forwarding(dp.id, ip_src, ip_dst, dp.id, dp2.id)
                    time.sleep(0.0005)
        end_out_time = time.time()
        out_total_ = end_out_time - out_time
        return

    def forwarding(self, dpid, ip_src, ip_dst, src_sw, dst_sw):
        """
            Get paths and install them into datapaths.
        """

        self.installed_paths.setdefault(dpid, {})
        path = self.get_path(str(src_sw), str(dst_sw))
        # her path : we dont care how she computed it where it is calculated ? 

        # for example between sw1 and sw2 there is a path, but how this path was built in the first place 
        # this path is about to change based on this part of the code
        """
        old
        dateDebut=70
        dateDebutCycle1 = 1000000
        dateDebutCycle2 = 60
        dateDebutCycle3 = 13000000

        new
        
        dateDebut=70
        dateDebutCycle1 = 1000000
        dateDebutCycle2 = 1000000
        dateDebutCycle3 = -1

        """
        dateDebut=70
        dateDebutCycle1 = 1000000
        dateDebutCycle2 = 1000000
        dateDebutCycle3 = 13000000

        Cycle1 = 0
        Cycle2 = 0
        Cycle3 = 0
    
        
        Seuil = random.uniform(0, 1)

        if self.count_monitor > dateDebutCycle1:
            Cycle1 = 1

        if self.count_monitor > dateDebutCycle2:
            Cycle2 = 1
            Cycle1 = 0

        if self.count_monitor > dateDebutCycle3:
            Cycle3 = 1
            Cycle2 = 0
            Cycle1 = 0

        NbrCheminChange = 0

        if (Cycle1 and self.count_monitor > dateDebutCycle1) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange +=1
            if ip_src == '10.0.0.1':
                if ip_dst == '10.0.0.2':
                    path = [1, 3, 14, 13, 19, 6, 7, 2] 
            if ip_src == '10.0.0.2':
                if ip_dst == '10.0.0.1':
                    path = [1, 3, 14, 13, 19, 6, 7, 2]
                    path.reverse()
                    
        if (Cycle1 and self.count_monitor > dateDebutCycle1) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange +=1
            if ip_src == '10.0.0.1':
                if ip_dst == '10.0.0.3':
                    # print("path avant", path)
                    # path = [1, 7, 2, 12, 22, 20, 15, 9, 16, 10, 3]
                    path = [1, 7, 6, 19, 13, 14, 3]
                    # print("path apres", path)
            if ip_src == '10.0.0.3':
                if ip_dst == '10.0.0.1':
                    # print("path avant", path)
                    # path = [1, 7, 2, 12, 22, 20, 15, 9, 16, 10, 3]
                    path = [1, 7, 6, 19, 13, 14, 3]
                    path.reverse()
                    # print("path apres", path)
        if (Cycle1 and self.count_monitor > dateDebutCycle1) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange +=1
            if ip_src == '10.0.0.1':
                if ip_dst == '10.0.0.4':
                    # print("path avant", path)
                    path = [1, 3, 14, 13, 19, 6, 7, 2, 4]
                    # print("path apres", path)
            if ip_src == '10.0.0.4':
                if ip_dst == '10.0.0.1':
                    # print("path avant", path)
                    path = [1, 3, 14, 13, 19, 6, 7, 2, 4]
                    path.reverse()
                    # print("path apres", path)

        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 5) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange +=1
            if ip_src == '10.0.0.1':
                if ip_dst == '10.0.0.5':
                    # print("path avant", path)
                    # path = [1, 7, 6, 19, 13, 17, 23, 2, 18, 21, 3, 11, 10, 12, 22, 20, 15, 9, 8, 5]
                    path = [1, 7, 6, 19, 13, 17, 10, 16, 5]
                    # print("path apres", path)
            if ip_src == '10.0.0.5':
                if ip_dst == '10.0.0.1':
                    # print("path avant", path)
                    # path = [1, 7, 6, 19, 13, 17, 23, 2, 18, 21, 3, 11, 10, 12, 22, 20, 15, 9, 8, 5]
                    path = [1, 7, 6, 19, 13, 17, 10, 16, 5]
                    path.reverse()
                    # print("path apres", path)
        if (Cycle1 and self.count_monitor > dateDebutCycle1 +5) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange +=1
            if ip_src == '10.0.0.1':
                if ip_dst == '10.0.0.6':
                    # print("path avant", path)
                    path = [1, 3, 14, 13, 19, 6]
                    # print("path apres", path)
            if ip_src == '10.0.0.6':
                if ip_dst == '10.0.0.1':
                    # print("path avant", path)
                    path = [1, 3, 14, 13, 19, 6]
                    path.reverse()
                    # print("path apres", path)
        if (Cycle1 and self.count_monitor > dateDebutCycle1 +5) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange +=1
            if ip_src == '10.0.0.1':
                if ip_dst == '10.0.0.7':
                    # print("path avant", path)
                    path = [1, 3, 14, 13, 19, 6, 7]
                    # print("path apres", path)
            if ip_src == '10.0.0.7':
                if ip_dst == '10.0.0.1':
                    # print("path avant", path)
                    path = [1, 3, 14, 13, 19, 6, 7]
                    path.reverse()
                    # print("path apres", path)
        if (Cycle1 and self.count_monitor > dateDebutCycle1 +5) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange +=1
            if ip_src == '10.0.0.1':
                if ip_dst == '10.0.0.8':
                    # print("path avant", path)
                    # path = [1, 7, 6, 19, 13, 14, 3, 11, 10, 17, 23, 2, 12, 22, 20, 15, 9, 8]
                    path = [1, 7, 6, 19, 13, 17, 10, 16, 5, 8]
                    # print("path apres", path)
            if ip_src == '10.0.0.8':
                if ip_dst == '10.0.0.1':
                    # print("path avant", path)
                    # path = [1, 7, 6, 19, 13, 14, 3, 11, 10, 17, 23, 2, 12, 22, 20, 15, 9, 8]
                    path = [1, 7, 6, 19, 13, 17, 10, 16, 5, 8]
                    path.reverse()
                    # print("path apres", path)

        if (Cycle1 and self.count_monitor > dateDebutCycle1 +10) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange +=1
            if ip_src == '10.0.0.1':
                if ip_dst == '10.0.0.9':
                    # print("path avant", path)
                    # path = [1, 7, 6, 19, 13, 17, 23, 2, 18, 21, 3, 11, 10, 12, 22, 20, 15, 9]
                    path = [1, 7, 6, 19, 13, 17, 10, 16, 9]
                    # print("path apres", path)
            if ip_src == '10.0.0.9':
                if ip_dst == '10.0.0.1':
                    # print("path avant", path)
                    # path = [1, 7, 6, 19, 13, 17, 23, 2, 18, 21, 3, 11, 10, 12, 22, 20, 15, 9]
                    path = [1, 7, 6, 19, 13, 17, 10, 16, 9]
                    path.reverse()
                    # print("path apres", path)
        if (Cycle1 and self.count_monitor > dateDebutCycle1 +10) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange +=1
            if ip_src == '10.0.0.1':
                if ip_dst == '10.0.0.10':
                    # print("path avant", path)
                    path = [1, 3, 14, 13, 19, 6, 7, 2, 12, 10]
                    # print("path apres", path)
            if ip_src == '10.0.0.10':
                if ip_dst == '10.0.0.1':
                    # print("path avant", path)
                    path = [1, 3, 14, 13, 19, 6, 7, 2, 12, 10]
                    path.reverse()
                    # print("path apres", path)
        if (Cycle1 and self.count_monitor > dateDebutCycle1 +10) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange +=1
            if ip_src == '10.0.0.1':
                if ip_dst == '10.0.0.11':
                    # print("path avant", path)
                    path = [1, 3, 14, 13, 19, 6, 7, 2, 12, 10, 11]
                    # print("path apres", path)
            if ip_src == '10.0.0.11':
                if ip_dst == '10.0.0.1':
                    # print("path avant", path)
                    path = [1, 3, 14, 13, 19, 6, 7, 2, 12, 10, 11]
                    path.reverse()
                    # print("path apres", path)
        if (Cycle1 and self.count_monitor > dateDebutCycle1 +10) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange +=1
            if ip_src == '10.0.0.1':
                if ip_dst == '10.0.0.12':
                    # print("path avant", path)
                    path = [1, 3, 14, 13, 19, 6, 7, 2, 12]
                    # print("path apres", path)
            if ip_src == '10.0.0.12':
                if ip_dst == '10.0.0.1':
                    # print("path avant", path)
                    path = [1, 3, 14, 13, 19, 6, 7, 2, 12]
                    path.reverse()
                    # print("path apres", path)
        if (Cycle1 and self.count_monitor > dateDebutCycle1 +10) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange +=1
            if ip_src == '10.0.0.1':
                if ip_dst == '10.0.0.13':
                    # print("path avant", path)
                    path = [1, 3, 14, 13]
                    # print("path apres", path)
            if ip_src == '10.0.0.13':
                if ip_dst == '10.0.0.1':
                    # print("path avant", path)
                    path = [1, 3, 14, 13]
                    path.reverse()
                    # print("path apres", path)
        if (Cycle1 and self.count_monitor > dateDebutCycle1 +10) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange +=1
            if ip_src == '10.0.0.1':
                if ip_dst == '10.0.0.14':
                    # print("path avant", path)
                    path = [1, 3, 14]
                    # print("path apres", path)
            if ip_src == '10.0.0.14':
                if ip_dst == '10.0.0.1':
                    # print("path avant", path)
                    path = [1, 3, 14]
                    path.reverse()
                    # print("path apres", path)

        if (Cycle1 and self.count_monitor > dateDebutCycle1 +15) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange +=1
            if ip_src == '10.0.0.1':
                if ip_dst == '10.0.0.15':
                    # print("path avant", path)
                    path = [1, 3, 14, 13, 19, 6, 7, 2, 4, 16, 5, 8, 9, 15]
                    # print("path apres", path)
            if ip_src == '10.0.0.15':
                if ip_dst == '10.0.0.1':
                    # print("path avant", path)
                    path = [1, 3, 14, 13, 19, 6, 7, 2, 4, 16, 5, 8, 9, 15]
                    path.reverse()
                    # print("path apres", path)
        if (Cycle1 and self.count_monitor > dateDebutCycle1 +15) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange +=1
            if ip_src == '10.0.0.1':
                if ip_dst == '10.0.0.16':
                    # print("path avant", path)
                    path = [1, 3, 14, 13, 19, 6, 7, 2, 4, 16]
                    # print("path apres", path)
            if ip_src == '10.0.0.16':
                if ip_dst == '10.0.0.1':
                    # print("path avant", path)
                    path = [1, 3, 14, 13, 19, 6, 7, 2, 4, 16]
                    path.reverse()
                    # print("path apres", path)
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 15) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.1':
                if ip_dst == '10.0.0.17':
                    # print("path avant", path)
                    path = [1, 3, 14, 13, 19, 6, 7, 17]
                    # print("path apres", path)
            if ip_src == '10.0.0.17':
                if ip_dst == '10.0.0.1':
                    # print("path avant", path)
                    path = [1, 3, 14, 13, 19, 6, 7, 17]
                    path.reverse()
                    # print("path apres", path)
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 15) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.1':
                if ip_dst == '10.0.0.18':
                    # print("path avant", path)
                    path = [1, 3, 14, 13, 19, 6, 7, 2, 18]
                    # print("path apres", path)
            if ip_src == '10.0.0.18':
                if ip_dst == '10.0.0.1':
                    # print("path avant", path)
                    path = [1, 3, 14, 13, 19, 6, 7, 2, 18]
                    path.reverse()
                    # print("path apres", path)
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 15) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.1':
                if ip_dst == '10.0.0.19':
                    # print("path avant", path)
                    path = [1, 3, 14, 13, 19]
                    # print("path apres", path)
            if ip_src == '10.0.0.19':
                if ip_dst == '10.0.0.1':
                    # print("path avant", path)
                    path = [1, 3, 14, 13, 19]
                    path.reverse()
                    # print("path apres", path)

        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 20) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.1':
                if ip_dst == '10.0.0.20':
                    # print("path avant", path)
                    path = [1, 3, 14, 13, 19, 6, 7, 17, 20]
                    # print("path apres", path)
            if ip_src == '10.0.0.20':
                if ip_dst == '10.0.0.1':
                    # print("path avant", path)
                    path = [1, 3, 14, 13, 19, 6, 7, 17, 20]
                    path.reverse()
                    # print("path apres", path)
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 20) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.1':
                if ip_dst == '10.0.0.21':
                    # print("path avant", path)
                    path = [1, 3, 14, 13, 19, 6, 7, 2, 18, 21]
                    # print("path apres", path)
            if ip_src == '10.0.0.21':
                if ip_dst == '10.0.0.1':
                    # print("path avant", path)
                    path = [1, 3, 14, 13, 19, 6, 7, 2, 18, 21]
                    path.reverse()
                    # print("path apres", path)
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 20) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.1':
                if ip_dst == '10.0.0.22':
                    # print("path avant", path)
                    path = [1, 3, 14, 13, 19, 6, 7, 2, 23, 17, 20, 22]
                    # print("path apres", path)
            if ip_src == '10.0.0.22':
                if ip_dst == '10.0.0.1':
                    # print("path avant", path)
                    path = [1, 3, 14, 13, 19, 6, 7, 2, 23, 17, 20, 22]
                    path.reverse()
                    # print("path apres", path)
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 20) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.1':
                if ip_dst == '10.0.0.23':
                    # print("path avant", path)
                    path = [1, 3, 14, 13, 19, 6, 7, 2, 23]
                    # print("path apres", path)
            if ip_src == '10.0.0.23':
                if ip_dst == '10.0.0.1':
                    # print("path avant", path)
                    path = [1, 3, 14, 13, 19, 6, 7, 2, 23]
                    path.reverse()
                    # print("path apres", path)


        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 25) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.2':
                if ip_dst == '10.0.0.3':
                    # print("path avant", path)
                    path = [2, 13, 14, 3]
                    # print("path apres", path)
            if ip_src == '10.0.0.3':
                if ip_dst == '10.0.0.2':
                    # print("path avant", path)
                    path = [2, 13, 14, 3]
                    path.reverse()
                    # print("path apres", path)
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 25) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.2':
                if ip_dst == '10.0.0.4':
                    # print("path avant", path)
                    # path = [2,23, 17, 13, 14, 3, 1, 7, 21, 3, 11, 10, 16, 4]
                    path = [2, 13, 14, 3, 10, 16, 4]
                    # print("path apres", path)
            if ip_src == '10.0.0.4':
                if ip_dst == '10.0.0.2':
                    # print("path avant", path)
                    # path = [2,23, 17, 13, 14, 3, 1, 7, 21, 3, 11, 10, 16, 4]
                    path = [2, 13, 14, 3, 10, 16, 4]
                    path.reverse()
                    # print("path apres", path)
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 25) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.2':
                if ip_dst == '10.0.0.5':
                    # print("path avant", path)
                    # path = [2,23, 17, 13, 14, 3, 1, 7, 21, 3, 11, 10, 16, 4]
                    path = [2, 13, 14, 3, 10, 16, 5]
                    # print("path apres", path)
            if ip_src == '10.0.0.5':
                if ip_dst == '10.0.0.2':
                    # print("path avant", path)
                    # path = [2,23, 17, 13, 14, 3, 1, 7, 21, 3, 11, 10, 16, 4]
                    path = [2, 13, 14, 3, 10, 16, 5]
                    path.reverse()
                    # print("path apres", path)
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 25) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.2':
                if ip_dst == '10.0.0.6':
                    # print("path avant", path)
                    # path = [2,23, 17, 13, 14, 3, 1, 7, 21, 3, 11, 10, 16, 4]
                    path = [2, 13, 14, 3, 1, 7, 6]
                    # print("path apres", path)
            if ip_src == '10.0.0.6':
                if ip_dst == '10.0.0.2':
                    # print("path avant", path)
                    # path = [2,23, 17, 13, 14, 3, 1, 7, 21, 3, 11, 10, 16, 4]
                    path = [2, 13, 14, 3, 1, 7, 6]
                    path.reverse()
                    # print("path apres", path)
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 25) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.2':
                if ip_dst == '10.0.0.7':
                    # print("path avant", path)
                    # path = [2,23, 17, 13, 14, 3, 1, 7, 21, 3, 11, 10, 16, 4]
                    path = [2, 13, 14, 3, 1, 7]
                    # print("path apres", path)
            if ip_src == '10.0.0.7':
                if ip_dst == '10.0.0.2':
                    # print("path avant", path)
                    # path = [2,23, 17, 13, 14, 3, 1, 7, 21, 3, 11, 10, 16, 4]
                    path = [2, 13, 14, 3, 1, 7]
                    path.reverse()
                    # print("path apres", path)
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 25) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.2':
                if ip_dst == '10.0.0.8':
                    # print("path avant", path)
                    # path = [9, 8, 5, 16, 10, 11, 3, 14, 13, 19, 6, 7, 17, 20, 22, 12, 2]
                    path = [2, 7, 6, 19, 13, 14, 3, 1, 16, 9, 8]
                    # print("path apres", path)
            if ip_src == '10.0.0.8':
                if ip_dst == '10.0.0.2':
                    # print("path avant", path)
                    # path = [9, 8, 5, 16, 10, 11, 3, 14, 13, 19, 6, 7, 17, 20, 22, 12, 2]
                    path = [2, 7, 6, 19, 13, 14, 3, 1, 16, 9, 8]
                    path.reverse()
                    # print("path apres", path)
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 30) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.2':
                if ip_dst == '10.0.0.9':
                    # print("path avant", path)
                    # path = [9, 8, 5, 16, 10, 11, 3, 14, 13, 19, 6, 7, 17, 20, 22, 12, 2]
                    path = [2, 7, 6, 19, 13, 14, 3, 1, 16, 9]
                    # print("path apres", path)
            if ip_src == '10.0.0.9':
                if ip_dst == '10.0.0.2':
                    # print("path avant", path)
                    # path = [9, 8, 5, 16, 10, 11, 3, 14, 13, 19, 6, 7, 17, 20, 22, 12, 2]
                    path = [2, 7, 6, 19, 13, 14, 3, 1, 16, 9]
                    path.reverse()
                    # print("path apres", path)
            #if ip_src == '10.0.0.2':
            #    if ip_dst == '10.0.0.10':
                    # print("path avant", path)
                    # path = [2,23, 17, 13, 14, 3, 1, 7, 21, 3, 11, 10, 16, 4]
            #        path = [2, 13, 14, 3, 1, 3, 10]
                    # print("path apres", path)
            #if ip_src == '10.0.0.10':
            #    if ip_dst == '10.0.0.2':
                    # print("path avant", path)
                    # path = [2,23, 17, 13, 14, 3, 1, 7, 21, 3, 11, 10, 16, 4]
            #        path = [2, 13, 14, 3, 1, 3, 10]
            #        path.reverse()
                    # print("path apres", path)
            #if ip_src == '10.0.0.2':
            #    if ip_dst == '10.0.0.11':
                    # print("path avant", path)
                    # path = [2,23, 17, 13, 14, 3, 1, 7, 21, 3, 11, 10, 16, 4]
            #        path = [2, 13, 14, 3, 1, 3, 10, 11]
                    # print("path apres", path)
            #if ip_src == '10.0.0.11':
            #    if ip_dst == '10.0.0.2':
                    # print("path avant", path)
                    # path = [2,23, 17, 13, 14, 3, 1, 7, 21, 3, 11, 10, 16, 4]
            #        path = [2, 13, 14, 3, 1, 3, 10, 11]
            #        path.reverse()
                    # print("path apres", path)
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 30) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.2':
                if ip_dst == '10.0.0.12':
                    # print("path avant", path)
                    # path = [2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 12]
                    path = [2, 13, 14, 3, 10, 12]
                    # print("path apres", path)
            if ip_src == '10.0.0.12':
                if ip_dst == '10.0.0.2':
                    # print("path avant", path)
                    # path = [2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 12]
                    path = [2, 13, 14, 3, 10, 12]
                    path.reverse()
                    # print("path apres", path)
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 30) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.2':
                if ip_dst == '10.0.0.13':
                    # print("path avant", path)
                    # path = [2,23, 17, 13, 14, 3, 1, 7, 21, 3, 11, 10, 16, 4]
                    path = [2, 13]
                    # print("path apres", path)
            if ip_src == '10.0.0.13':
                if ip_dst == '10.0.0.2':
                    # print("path avant", path)
                    # path = [2,23, 17, 13, 14, 3, 1, 7, 21, 3, 11, 10, 16, 4]
                    path = [2, 13]
                    path.reverse()
                    # print("path apres", path)
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 30) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.2':
                if ip_dst == '10.0.0.14':
                    # print("path avant", path)
                    # path = [2,23, 17, 13, 14, 3, 1, 7, 21, 3, 11, 10, 16, 4]
                    path = [2, 13, 14]
                    # print("path apres", path)
            if ip_src == '10.0.0.14':
                if ip_dst == '10.0.0.2':
                    # print("path avant", path)
                    # path = [2,23, 17, 13, 14, 3, 1, 7, 21, 3, 11, 10, 16, 4]
                    path = [2, 13, 14]
                    path.reverse()
                    # print("path apres", path)
            #if ip_src == '10.0.0.2':
            #    if ip_dst == '10.0.0.15':
                    # print("path avant", path)
                    # path = [2,23, 17, 13, 14, 3, 1, 7, 21, 3, 11, 10, 16, 4]
            #        path = [2, 13, 14, 3, 1, 3, 10, 16, 9, 15]
                    # print("path apres", path)
            #if ip_src == '10.0.0.15':
            #    if ip_dst == '10.0.0.2':
                    # print("path avant", path)
                    # path = [2,23, 17, 13, 14, 3, 1, 7, 21, 3, 11, 10, 16, 4]
            #        path = [2, 13, 14, 3, 1, 3, 10, 16, 9, 15]
            #        path.reverse()
                    # print("path apres", path)
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 35) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.2':
                if ip_dst == '10.0.0.16':
                    # print("path avant", path)
                    # path = [2,23, 17, 13, 14, 3, 1, 7, 21, 3, 11, 10, 16, 4]
                    path = [2, 13, 14, 3, 1, 3, 10, 16]
                    # print("path apres", path)
            if ip_src == '10.0.0.16':
                if ip_dst == '10.0.0.2':
                    # print("path avant", path)
                    # path = [2,23, 17, 13, 14, 3, 1, 7, 21, 3, 11, 10, 16, 4]
                    path = [2, 13, 14, 3, 1, 3, 10, 16]
                    path.reverse()
                    # print("path apres", path)
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 35) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.2':
                if ip_dst == '10.0.0.17':
                    # print("path avant", path)
                    # path = [2,23, 17, 13, 14, 3, 1, 7, 21, 3, 11, 10, 16, 4]
                    path = [2, 13, 14, 3, 1, 7, 17]
                    # print("path apres", path)
            if ip_src == '10.0.0.17':
                if ip_dst == '10.0.0.2':
                    # print("path avant", path)
                    # path = [2,23, 17, 13, 14, 3, 1, 7, 21, 3, 11, 10, 16, 4]
                    path = [2, 13, 14, 3, 1, 7, 17]
                    path.reverse()
                    # print("path apres", path)
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 35) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.2':
                if ip_dst == '10.0.0.18':
                    # print("path avant", path)
                    # path = [2, 23, 17, 20, 15, 9, 16, 1, 7, 21, 18]
                    path = [2, 13, 14, 3, 1, 7, 21, 18]
                    # print("path apres", path)
            if ip_src == '10.0.0.18':
                if ip_dst == '10.0.0.2':
                    # print("path avant", path)
                    # path = [2, 23, 17, 20, 15, 9, 16, 1, 7, 21, 18]
                    path = [2, 13, 14, 3, 1, 7, 21, 18]
                    path.reverse()
                    # print("path apres", path)
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 35) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.2':
                if ip_dst == '10.0.0.19':
                    # print("path avant", path)
                    # path = [2, 23, 17, 20, 15, 9, 16, 1, 7, 21, 18]
                    path = [2, 13, 19]
                    # print("path apres", path)
            if ip_src == '10.0.0.19':
                if ip_dst == '10.0.0.2':
                    # print("path avant", path)
                    # path = [2, 23, 17, 20, 15, 9, 16, 1, 7, 21, 18]
                    path = [2, 13, 19]
                    path.reverse()
                    # print("path apres", path)
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 35) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.2':
                if ip_dst == '10.0.0.20':
                    # print("path avant", path)
                    # path = [2, 23, 17, 20, 15, 9, 16, 1, 7, 21, 18]
                    path = [2, 13, 14, 3, 1, 7, 17, 20]
                    # print("path apres", path)
            if ip_src == '10.0.0.20':
                if ip_dst == '10.0.0.2':
                    # print("path avant", path)
                    # path = [2, 23, 17, 20, 15, 9, 16, 1, 7, 21, 18]
                    path = [2, 13, 14, 3, 1, 7, 17, 20]
                    path.reverse()
                    # print("path apres", path)
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 35) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.2':
                if ip_dst == '10.0.0.21':
                    # print("path avant", path)
                    # path = [2, 23, 17, 20, 15, 9, 16, 1, 7, 21, 18]
                    path = [2, 13, 14, 3, 1, 7, 21]
                    # print("path apres", path)
            if ip_src == '10.0.0.21':
                if ip_dst == '10.0.0.2':
                    # print("path avant", path)
                    # path = [2, 23, 17, 20, 15, 9, 16, 1, 7, 21, 18]
                    path = [2, 13, 14, 3, 1, 7, 21]
                    path.reverse()
                    # print("path apres", path)
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 35) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.2':
                if ip_dst == '10.0.0.22':
                    # print("path avant", path)
                    # path = [2, 23, 17, 20, 15, 9, 16, 1, 7, 21, 18]
                    path = [2, 13, 14, 3, 1, 7, 17, 20, 22]
                    # print("path apres", path)
            if ip_src == '10.0.0.22':
                if ip_dst == '10.0.0.2':
                    # print("path avant", path)
                    # path = [2, 23, 17, 20, 15, 9, 16, 1, 7, 21, 18]
                    path = [2, 13, 14, 3, 1, 7, 17, 20, 22]
                    path.reverse()
                    # print("path apres", path)
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 35) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.2':
                if ip_dst == '10.0.0.23':
                    # print("path avant", path)
                    # path = [2, 23, 17, 20, 15, 9, 16, 1, 7, 21, 18]
                    path = [2, 13, 14, 3, 1, 7, 17, 23]
                    # print("path apres", path)
            if ip_src == '10.0.0.23':
                if ip_dst == '10.0.0.2':
                    # print("path avant", path)
                    # path = [2, 23, 17, 20, 15, 9, 16, 1, 7, 21, 18]
                    path = [2, 13, 14, 3, 1, 7, 17, 23]
                    path.reverse()
                    # print("path apres", path)

        ################## the previous was for switches 1,2 ###########
        ################# the followings for switches until 23 #########

        i = 4
        j = 3

        # Pour sw = 3

        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13, 19, 6, 7, 2, 4]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13, 19, 6, 7, 2, 4]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.3':
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13, 19, 6, 7, 2, 4, 16, 5]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.3':
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13, 19, 6, 7, 2, 4, 16, 5]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.3':
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13, 19, 6]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.3':
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13, 19, 6]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.3':
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13, 19, 6, 7]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.3':
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13, 19, 6, 7]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.3':
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13, 19, 6, 7, 2, 4, 16, 5, 8]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.3':
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13, 19, 6, 7, 2, 4, 16, 5, 8]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.3':
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13, 19, 6, 7, 2, 4, 16, 9]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.3':
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13, 19, 6, 7, 2, 4, 16, 9]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.3':
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13, 19, 6, 7, 2, 12, 10]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.3':
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13, 19, 6, 7, 2, 12, 10]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.3':
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13, 19, 6, 7, 17, 10, 11]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.3':
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13, 19, 6, 7, 17, 10, 11]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.3':
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13, 19, 6, 7, 2, 12]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.3':
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13, 19, 6, 7, 2, 12]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 5) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.3':
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.3':
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 5) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.3':
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.3':
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 5) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.3':
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13, 19, 6, 7, 2, 4, 16, 9, 15]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.3':
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13, 19, 6, 7, 2, 4, 16, 9, 15]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 5) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.3':
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13, 19, 6, 7, 2, 4, 16]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.3':
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13, 19, 6, 7, 2, 4, 16]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 10) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.3':
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13, 19, 6, 7, 2, 23, 17]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.3':
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13, 19, 6, 7, 2, 23, 17]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 10) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.3':
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13, 19, 6, 7, 2, 18]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.3':
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13, 19, 6, 7, 2, 18]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 10) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.3':
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13, 19]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.3':
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13, 19]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 10) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.3':
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13, 19, 6, 7, 17, 20]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.3':
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13, 19, 6, 7, 17, 20]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 30) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.3':
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13, 19, 6, 7, 21]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.3':
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13, 19, 6, 7, 21]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 30) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.3':
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13, 19, 6, 7, 2, 12, 22]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.3':
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13, 19, 6, 7, 2, 12, 22]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 30) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.3':
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13, 19, 6, 7, 2, 23]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.3':
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [3, 14, 13, 19, 6, 7, 2, 23]
                    path.reverse()
                    # print("path apres", path)


        i=5
        j+=1

        # Pour sw = 4

        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 70) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    path = [4, 2, 13, 14, 3, 1, 16, 5]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13, 14, 3, 1, 16, 5]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 70) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13, 19, 6]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13, 19, 6]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 70) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13, 14, 3, 1, 7]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13, 14, 3, 1, 7]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 10) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13, 14, 3, 1, 16, 5, 8]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13, 14, 3, 1, 16, 5, 8]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 5) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13, 14, 3, 1, 16, 9]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13, 14, 3, 1, 16, 9]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 30) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13, 14, 3, 11, 10]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13, 14, 3, 11, 10]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 25) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13, 14, 3, 11]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13, 14, 3, 11]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 70) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13, 14, 3, 11, 10, 12]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13, 14, 3, 11, 10, 12]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 15) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 30) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13, 14]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13, 14]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 20) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13, 14, 3, 11, 10, 16, 9, 15]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13, 14, 3, 11, 10, 16, 9, 15]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 20) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13, 14, 3, 11, 10, 16]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13, 14, 3, 11, 10, 16]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 15) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13, 14, 3, 1, 7, 17]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13, 14, 3, 1, 7, 17]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 5) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13, 14, 3, 1, 7, 21, 18]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13, 14, 3, 1, 7, 21, 18]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 10) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13, 14, 3, 1, 7, 19]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13, 14, 3, 1, 7, 19]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 30) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13, 14, 3, 1, 7, 17, 20]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13, 14, 3, 1, 7, 17, 20]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 50) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13, 14, 3, 1, 7, 21]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13, 14, 3, 1, 7, 21]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 10) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13, 14, 3, 1, 7, 17, 20, 22]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13, 14, 3, 1, 7, 17, 20, 22]
                    path.reverse()
                    # print("path apres", path)
        i+=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 25) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13, 14, 3, 1, 7, 17, 23]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [4, 2, 13, 14, 3, 1, 7, 17, 23]
                    path.reverse()
                    # print("path apres", path)

        j+=1
        i = 6

        # Pour sw 5

        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 35) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [5, 16, 4, 2, 13, 19, 6]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [5, 16, 4, 2, 13, 19, 6]
                    path.reverse()
                    # print("path apres", path)
        i +=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 15) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [5, 16, 4, 2, 13, 19, 6, 7]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [5, 16, 4, 2, 13, 19, 6, 7]
                    path.reverse()
                    # print("path apres", path)
        i +=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 20) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [5, 8]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [5, 8]
                    path.reverse()
                    # print("path apres", path)
        i +=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 25) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [5, 8, 9]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [5, 8, 9]
                    path.reverse()
                    # print("path apres", path)
        i +=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 5) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [5, 16, 4, 2, 13, 14, 3, 10]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [5, 16, 4, 2, 13, 14, 3, 10]
                    path.reverse()
                    # print("path apres", path)
        i +=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 10) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [5, 16, 4, 2, 13, 14, 3, 10, 11]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [5, 16, 4, 2, 13, 14, 3, 10, 11]
                    path.reverse()
                    # print("path apres", path)
        i +=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 10) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [5, 16, 4, 2, 13, 14, 3, 10, 12]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    path = [5, 16, 4, 2, 13, 14, 3, 10, 12]
                    path.reverse()
                    # print("path apres", path)
        i +=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 70) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    path = [5, 16, 4, 2, 13]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    path = [5, 16, 4, 2, 13]
                    path.reverse()
                    # print("path apres", path)
        i +=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    path = [5, 16, 4, 2, 13, 14]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    path = [5, 16, 4, 2, 13, 14]
                    path.reverse()
                    # print("path apres", path)
        i +=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    path = [5, 8, 9, 15]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    path = [5, 8, 9, 15]
                    path.reverse()
                    # print("path apres", path)
        i +=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    path = [5, 16]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    path = [5, 16]
                    path.reverse()
                    # print("path apres", path)
        i +=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 80) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    path = [5, 16, 4, 2, 13, 14, 3, 1, 7, 17]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    path = [5, 16, 4, 2, 13, 14, 3, 1, 7, 17]
                    path.reverse()
                    # print("path apres", path)
        i +=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 80) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    path = [5, 16, 4, 2, 13, 14, 3, 1, 7, 2, 18]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    path = [5, 16, 4, 2, 13, 14, 3, 1, 7, 2, 18]
                    path.reverse()
                    # print("path apres", path)
        i +=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    path = [5, 16, 4, 2, 13, 19]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    path = [5, 16, 4, 2, 13, 19]
                    path.reverse()
                    # print("path apres", path)
        i +=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    path = [5, 8, 9, 15, 20]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    path = [5, 8, 9, 15, 20]
                    path.reverse()
                    # print("path apres", path)
        i +=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 10) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    path = [5, 16, 4, 2, 13, 14, 3, 1, 7, 21]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    path = [5, 16, 4, 2, 13, 14, 3, 1, 7, 21]
                    path.reverse()
                    # print("path apres", path)
        i +=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    path = [5, 16, 4, 2, 13, 14, 3, 1, 7, 17, 20, 22]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    path = [5, 16, 4, 2, 13, 14, 3, 1, 7, 17, 20, 22]
                    path.reverse()
                    # print("path apres", path)
        i +=1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 10) or (Cycle2 and random.uniform(0, 1)> Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.'+str(j):
                if ip_dst == '10.0.0.'+str(i):
                    # print("path avant", path)
                    path = [5, 16, 4, 2, 13, 14, 3, 1, 7, 17, 23]
                    # print("path apres", path)
            if ip_src == '10.0.0.'+str(i):
                if ip_dst == '10.0.0.'+str(j):
                    # print("path avant", path)
                    path = [5, 16, 4, 2, 13, 14, 3, 1, 7, 17, 23]
                    path.reverse()
                    # print("path apres", path)

        j += 1
        i = 7

        # Pour sw 6

        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [6, 7]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [6, 7]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [6, 19, 13, 2, 4, 16, 5, 8]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [6, 19, 13, 2, 4, 16, 5, 8]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [6, 19, 13, 2, 4, 16, 9]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [6, 19, 13, 2, 4, 16, 9]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [6, 19, 13, 17, 10]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [6, 19, 13, 17, 10]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [6, 19, 13, 17, 10, 11]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [6, 19, 13, 17, 10, 11]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [6, 19, 13, 17, 10, 12]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [6, 19, 13, 17, 10, 12]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [6, 19, 13]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [6, 19, 13]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [6, 19, 13, 14]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [6, 19, 13, 14]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [6, 19, 13, 17, 10, 16, 9, 15]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [6, 19, 13, 17, 10, 16, 9, 15]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [6, 19, 13, 17, 10, 16]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [6, 19, 13, 17, 10, 16]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [6, 19, 13, 17]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [6, 19, 13, 17]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 10) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [6, 19, 13, 17, 23, 2, 18]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [6, 19, 13, 17, 23, 2, 18]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [6, 19]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [6, 19]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [6, 19, 13, 17, 20]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [6, 19, 13, 17, 20]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 10) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [6, 7, 21]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [6, 7, 21]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [6, 7, 17, 20, 22]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [6, 7, 17, 20, 22]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [6, 7, 17, 23]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [6, 7, 17, 23]
                    path.reverse()
                    # print("path apres", path)

        j += 1
        i = 8

        # Pour sw 7

        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [7, 6,19, 13, 14, 3, 1, 16, 5, 8]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [7, 6,19, 13, 14, 3, 1, 16, 5, 8]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [7, 6,19, 13, 14, 3, 1, 16, 9]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [7, 6,19, 13, 14, 3, 1, 16, 9]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [7, 6,19, 13, 14, 3, 11, 10]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [7, 6,19, 13, 14, 3, 11, 10]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [7, 6,19, 13, 14, 3, 11]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [7, 6,19, 13, 14, 3, 11]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [7, 6,19, 13, 14, 3, 11, 10, 12]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [7, 6,19, 13, 14, 3, 11, 10, 12]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [7, 6,19, 13]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [7, 6,19, 13]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [7, 6,19, 13, 14]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [7, 6,19, 13, 14]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [7, 6,19, 13, 14, 3, 1, 16, 9, 15]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [7, 6,19, 13, 14, 3, 1, 16, 9, 15]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [7, 6,19, 13, 14, 3, 1, 16]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [7, 6,19, 13, 14, 3, 1, 16]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [7, 6,19, 13, 14, 3, 1, 7, 17]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [7, 6,19, 13, 14, 3, 1, 7, 17]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [7, 6,19, 13, 14, 3, 1, 7, 21, 18]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [7, 6,19, 13, 14, 3, 1, 7, 21, 18]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [7, 6,19]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [7, 6, 19]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [7, 6,19, 13, 14, 3, 1, 7, 17, 20]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [7, 6,19, 13, 14, 3, 1, 7, 17, 20]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [7, 6,19, 13, 14, 3, 1, 7, 21]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [7, 6,19, 13, 14, 3, 1, 7, 21]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [7, 6,19, 13, 14, 3, 1, 7, 17, 20, 22]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [7, 6,19, 13, 14, 3, 1, 7, 17, 20, 22]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [7, 6,19, 13, 14, 3, 1, 7, 17, 23]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [7, 6,19, 13, 14, 3, 1, 7, 17, 23]
                    path.reverse()
                    # print("path apres", path)

        j += 1
        i = 9

        # Pour sw 8

        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [8, 9]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [8, 9]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [8, 5, 16, 1, 3, 14, 13, 17, 10]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [8, 5, 16, 1, 3, 14, 13, 17, 10]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [8, 5, 16, 1, 3, 14, 13, 17, 10, 11]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [8, 5, 16, 1, 3, 14, 13, 17, 10, 11]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [8, 5, 16, 1, 3, 14, 13, 17, 10, 12]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [8, 5, 16, 1, 3, 14, 13, 17, 10, 12]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [8, 5, 16, 1, 3, 14, 13]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [8, 5, 16, 1, 3, 14, 13]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [8, 5, 16, 1, 3, 14]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [8, 5, 16, 1, 3, 14]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [8, 9, 15]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [8, 9, 15]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [8, 5, 16, 1, 3, 14, 13, 17, 10, 16]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [8, 5, 16, 1, 3, 14, 13, 17, 10, 16]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [8, 5, 16, 4, 2, 7, 6, 19, 13, 17]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [8, 5, 16, 4, 2, 7, 6, 19, 13, 17]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [8, 5, 16, 1, 3, 14, 13, 17, 23, 2, 18]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [8, 5, 16, 1, 3, 14, 13, 17, 23, 2, 18]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [8, 5, 16, 1, 3, 14, 13, 19]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [8, 5, 16, 1, 3, 14, 13, 19]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [8, 5, 16, 1, 3, 14, 13, 17, 20]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [8, 5, 16, 1, 3, 14, 13, 17, 20]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [8, 5, 16, 1, 3, 14, 13, 19, 7, 21]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [8, 5, 16, 1, 3, 14, 13, 19, 7, 21]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [8, 5, 16, 1, 3, 14, 13, 2, 12, 22]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [8, 5, 16, 1, 3, 14, 13, 2,  12, 22]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [8, 5, 16, 1, 3, 14, 13, 17, 23]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [8, 5, 16, 1, 3, 14, 13, 17, 23]
                    path.reverse()
                    # print("path apres", path)

        j += 1
        i = 10

        # Pour sw 9

        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [9, 16, 1, 3, 14, 13, 17, 10]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [9, 16, 1, 3, 14, 13, 17, 10]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [9, 16, 1, 3, 14, 13, 17, 10, 11]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [9, 16, 1, 3, 14, 13, 17, 10, 11]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [9, 16, 1, 3, 14, 13, 19, 6, 7, 2, 12]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [9, 16, 1, 3, 14, 13, 19, 6, 7, 2, 12]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [9, 16, 1, 3, 14, 13]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [9, 16, 1, 3, 14, 13]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [9, 16, 1, 3, 14]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [9, 16, 1, 3, 14]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [9, 15]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [9, 15]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [9, 16]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [9, 16]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [9, 16, 4, 2, 7, 6, 19, 13, 17]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [9, 16, 4, 2, 7, 6, 19, 13, 17]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [9, 16, 1, 3, 14, 13, 17, 23, 2, 18]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [9, 16, 1, 3, 14, 13, 17, 23, 2, 18]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [9, 16, 1, 3, 14, 13, 19]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [9, 16, 1, 3, 14, 13, 19]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [9, 16, 1, 3, 14, 13, 17, 20]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [9, 16, 1, 3, 14, 13, 17, 20]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [9, 16, 1, 3, 14, 13, 19, 7, 21]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [9, 16, 1, 3, 14, 13, 19, 7, 21]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [9, 16, 1, 3, 14, 13, 2,  12, 22]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [9, 16, 1, 3, 14, 13, 2,  12, 22]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [9, 16, 1, 3, 14, 13, 17, 23]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [9, 16, 1, 3, 14, 13, 17, 23]
                    path.reverse()
                    # print("path apres", path)


        j += 1
        i = 11

        # Pour sw 10

        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    # path = [3, 14, 13,19, 6, 7, 21, 18, 2, 23, 17, 20, 15, 9, 8, 5, 16, 10, 11]
                    path = [10, 17, 13, 14, 3, 11]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [10, 17, 13, 14, 3, 11]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [10, 17, 13, 14, 3, 1, 7, 2, 12]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [10, 17, 13, 14, 3, 1, 7, 2, 12]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [10, 17, 13]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [10, 17, 13]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [10, 17, 13, 14]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [10, 17, 13, 14]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [10, 17, 13, 14, 3, 1, 7, 2, 23, 17, 20, 15]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [10, 17, 13, 14, 3, 1, 7, 2, 23, 17, 20, 15]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [10, 17, 13, 14, 3, 1, 7, 2, 4, 16]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [10, 17, 13, 14, 3, 1, 7, 2, 4, 16]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [10, 17]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [10, 17]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [10, 17, 13, 14, 3, 1, 7, 21, 18]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [10, 17, 13, 14, 3, 1, 7, 21, 18]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [10, 17, 13, 14, 3, 1, 7, 19]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [10, 17, 13, 14, 3, 1, 7, 19]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [10, 17, 20]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [10, 17, 20]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [10, 17, 13, 14, 3, 1, 7, 21]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [10, 17, 13, 14, 3, 1, 7, 21]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [10, 17, 20, 22]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [10, 17, 20, 22]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [10, 17, 13, 14, 3, 1, 7, 2, 23]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [10, 17, 13, 14, 3, 1, 7, 2, 23]
                    path.reverse()
                    # print("path apres", path)


        j += 1
        i = 12

        # Pour sw 11

        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [11, 10, 17, 13, 14, 3, 1, 7, 2, 12]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [11, 10, 17, 13, 14, 3, 1, 7, 2, 12]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [11, 10, 17, 13]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [11, 10, 17, 13]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [11, 10, 17, 13, 14]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [11, 10, 17, 13, 14]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [11, 10, 17, 13, 14, 3, 1, 7, 2, 23, 17, 20, 15]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [11, 10, 17, 13, 14, 3, 1, 7, 2, 23, 17, 20, 15]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [11, 10, 17, 13, 14, 3, 1, 7, 2, 4, 16]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [11, 10, 17, 13, 14, 3, 1, 7, 2, 4, 16]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [11, 3, 14, 13, 19, 6, 7, 17]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [11, 3, 14, 13, 19, 6, 7, 17]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [11, 10, 17, 13, 14, 3, 1, 7, 21, 18]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [11, 10, 17, 13, 14, 3, 1, 7, 21, 18]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [11, 10, 17, 13, 14, 3, 1, 7, 19]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [11, 10, 17, 13, 14, 3, 1, 7, 19]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [11, 10, 17, 20]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [11, 10, 17, 20]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [11, 10, 17, 13, 14, 3, 1, 7, 21]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [11, 10, 17, 13, 14, 3, 1, 7, 21]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [11, 10, 17, 20, 22]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [11, 10, 17, 20, 22]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [11, 10, 17, 13, 14, 3, 1, 7, 2, 23]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [11, 10, 17, 13, 14, 3, 1, 7, 2, 23]
                    path.reverse()
                    # print("path apres", path)




        j += 1
        i = 13

        # Pour sw 12


        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [12, 10, 17, 13]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [12, 10, 17, 13]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [12, 10, 17, 13, 14]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [12, 10, 17, 13, 14]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [12, 10, 17, 13, 14, 3, 1, 7, 2, 23, 17, 20, 15]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [12, 10, 17, 13, 14, 3, 1, 7, 2, 23, 17, 20, 15]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [12, 10, 17, 13, 14, 3, 1, 7, 2, 4, 16]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [12, 10, 17, 13, 14, 3, 1, 7, 2, 4, 16]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [12, 10, 11, 3, 14, 13, 19, 6, 7, 17]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [12, 10, 11, 3, 14, 13, 19, 6, 7, 17]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [12, 10, 17, 13, 14, 3, 1, 7, 21, 18]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [12, 10, 17, 13, 14, 3, 1, 7, 21, 18]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [12, 10, 17, 13, 14, 3, 1, 7, 19]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [12, 10, 17, 13, 14, 3, 1, 7, 19]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [12, 10, 17, 20]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [12, 10, 17, 20]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [12, 10, 17, 13, 14, 3, 1, 7, 21]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [12, 10, 17, 13, 14, 3, 1, 7, 21]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [12, 10, 17, 20, 22]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [12, 10, 17, 20, 22]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [12, 10, 17, 13, 14, 3, 1, 7, 2, 23]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [12, 10, 17, 13, 14, 3, 1, 7, 2, 23]
                    path.reverse()
                    # print("path apres", path)




        j += 1
        i = 14

        # Pour sw 13


        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [13, 14]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [13, 14]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [13, 14, 3, 1, 7, 2, 23, 17, 20, 15]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [13, 14, 3, 1, 7, 2, 23, 17, 20, 15]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [13, 14, 3, 1, 7, 2, 4, 16]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [13, 14, 3, 1, 7, 2, 4, 16]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [13, 14, 3, 1, 7, 17]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [13, 14, 3, 1, 7, 17]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [13, 14, 3, 1, 7, 21, 18]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [13, 14, 3, 1, 7, 21, 18]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [13, 14, 3, 1, 7, 19]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [13, 14, 3, 1, 7, 19]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [13, 14, 3, 1, 7, 17, 20]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [13, 14, 3, 1, 7, 17, 20]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [13, 14, 3, 1, 7, 21]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [13, 14, 3, 1, 7, 21]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [13, 14, 3, 1, 7, 17, 20, 22]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [13, 14, 3, 1, 7, 17, 20, 22]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [13, 14, 3, 1, 7, 2, 23]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [13, 14, 3, 1, 7, 2, 23]
                    path.reverse()
                    # print("path apres", path)

        j += 1
        i = 15

        # Pour sw 14


        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [14, 3, 1, 7, 2, 23, 17, 20, 15]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [14, 3, 1, 7, 2, 23, 17, 20, 15]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [14, 3, 1, 7, 2, 4, 16]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [14, 3, 1, 7, 2, 4, 16]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [14, 3, 1, 7, 17]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [14, 3, 1, 7, 17]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [14, 3, 1, 7, 21, 18]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [14, 3, 1, 7, 21, 18]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [14, 3, 1, 7, 19]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [14, 3, 1, 7, 19]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [14, 3, 1, 7, 17, 20]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [14, 3, 1, 7, 17, 20]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [14, 3, 1, 7, 21]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [14, 3, 1, 7, 21]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [14, 3, 1, 7, 17, 20, 22]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [14, 3, 1, 7, 17, 20, 22]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [14, 3, 1, 7, 2, 23]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [14, 3, 1, 7, 2, 23]
                    path.reverse()
                    # print("path apres", path)

        j += 1
        i = 16

        # Pour sw 15

        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [15, 9, 16]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [15, 9, 16]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [15, 9, 16, 4, 2, 7, 6, 19, 13, 17]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [15, 9, 16, 4, 2, 7, 6, 19, 13, 17]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [15, 9, 16, 1, 3, 14, 13, 17, 23, 2, 18]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [15, 9, 16, 1, 3, 14, 13, 17, 23, 2, 18]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [15, 9, 16, 1, 3, 14, 13, 19]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [15, 9, 16, 1, 3, 14, 13, 19]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [15, 9, 16, 1, 3, 14, 13, 17, 20]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [15, 9, 16, 1, 3, 14, 13, 17, 20]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [15, 9, 16, 1, 3, 14, 13, 19, 7, 21]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [15, 9, 16, 1, 3, 14, 13, 19, 7, 21]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [15, 9, 16, 1, 3, 14, 13, 2,  12, 22]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [15, 9, 16, 1, 3, 14, 13, 2,  12, 22]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [15, 9, 16, 1, 3, 14, 13, 17, 23]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [15, 9, 16, 1, 3, 14, 13, 17, 23]
                    path.reverse()
                    # print("path apres", path)


        j += 1
        i = 17

        # Pour sw 16

        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [16, 4, 2, 7, 6, 19, 13, 17]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [16, 4, 2, 7, 6, 19, 13, 17]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [16, 1, 3, 14, 13, 17, 23, 2, 18]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [16, 1, 3, 14, 13, 17, 23, 2, 18]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [16, 1, 3, 14, 13, 19]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [16, 1, 3, 14, 13, 19]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [16, 1, 3, 14, 13, 17, 20]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [16, 1, 3, 14, 13, 17, 20]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [16, 1, 3, 14, 13, 19, 7, 21]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [16, 1, 3, 14, 13, 19, 7, 21]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [16, 1, 3, 14, 13, 2,  12, 22]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [16, 1, 3, 14, 13, 2,  12, 22]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [16, 1, 3, 14, 13, 17, 23]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [16, 1, 3, 14, 13, 17, 23]
                    path.reverse()
                    # print("path apres", path)

        j += 1
        i = 18

        # Pour sw 17

        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [17, 13, 14, 3, 1, 7, 21, 18]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [17, 13, 14, 3, 1, 7, 21, 18]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [17, 13, 14, 3, 1, 7, 19]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [17, 13, 14, 3, 1, 7, 19]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [17, 20]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [17, 20]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [17, 13, 14, 3, 1, 7, 21]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [17, 13, 14, 3, 1, 7, 21]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [17, 20, 22]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [17, 20, 22]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [17, 13, 14, 3, 1, 7, 2, 23]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [17, 13, 14, 3, 1, 7, 2, 23]
                    path.reverse()
                    # print("path apres", path)


        j += 1
        i = 19

        # Pour sw 18


        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [18, 2, 23, 17, 13, 14, 3, 1, 7, 19]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [18, 2, 23, 17, 13, 14, 3, 1, 7, 19]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [18, 2, 23, 17, 20]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [18, 2, 23, 17, 20]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [18, 2, 23, 17, 13, 14, 3, 1, 7, 21]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [18, 2, 23, 17, 13, 14, 3, 1, 7, 21]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [18, 2, 23, 17, 20, 22]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [18, 2, 23, 17, 20, 22]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [18, 2, 23]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [18, 2, 23]
                    path.reverse()
                    # print("path apres", path)

        j += 1
        i = 20

        # Pour sw 19

        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [19, 13, 14, 3, 1, 7, 17, 20]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [19, 13, 14, 3, 1, 7, 17, 20]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [19, 13, 14, 3, 1, 7, 21]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [19, 13, 14, 3, 1, 7, 21]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [19, 13, 14, 3, 1, 7, 17, 20, 22]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [19, 13, 14, 3, 1, 7, 17, 20, 22]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [19, 13, 14, 3, 1, 7, 2, 23]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [19, 13, 14, 3, 1, 7, 2, 23]
                    path.reverse()
                    # print("path apres", path)


        j += 1
        i = 21

        # Pour sw 20

        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [20, 17, 13, 14, 3, 1, 7, 21]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [20, 17, 13, 14, 3, 1, 7, 21]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [20, 22]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [20, 22]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [20, 17, 13, 14, 3, 1, 7, 2, 23]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [20, 17, 13, 14, 3, 1, 7, 2, 23]
                    path.reverse()
                    # print("path apres", path)



        j += 1
        i = 22

        # Pour sw 21

        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [21, 7, 1, 3, 14, 13, 17, 20, 22]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [21, 7, 1, 3, 14, 13, 17, 20, 22]
                    path.reverse()
                    # print("path apres", path)
        i += 1
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [21, 7, 1, 3, 14, 13, 17, 23]
                    # print("path apres", path)
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [21, 7, 1, 3, 14, 13, 17, 23]
                    path.reverse()
                    # print("path apres", path)



        j += 1
        i = 23

        # Pour sw 22

        ########## here is the path after their calculation ###########
    
        if (Cycle1 and self.count_monitor > dateDebutCycle1 + 40) or (
                Cycle2 and random.uniform(0, 1) > Seuil) or Cycle3:
            NbrCheminChange += 2
            if ip_src == '10.0.0.' + str(j):
                if ip_dst == '10.0.0.' + str(i):
                    # print("path avant", path)
                    path = [22, 20, 17, 23]
                    # print("path apres", path)
            
            if ip_src == '10.0.0.' + str(i):
                if ip_dst == '10.0.0.' + str(j):
                    # print("path avant", path)
                    path = [22, 20, 17, 23]
                    path.reverse()
                    # print("path apres", path)


        writetoCSV = [self.count_monitor, NbrCheminChange]
        with open("NbrCheminChange.csv", "a") as file:
            writer = csv.writer(file, quoting = csv.QUOTE_ALL, delimiter = ';')
            writer.writerows([writetoCSV])

        self.installed_paths[src_sw][dst_sw] = path
        flow_info = (ip_src, ip_dst)
        self.install_flow(self.datapaths, self.awareness.link_to_port, path, flow_info)

    def request_stats(self, datapath): #OK
        self.logger.debug('send stats request: %016x', datapath.id)
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        req = parser.OFPPortDescStatsRequest(datapath, 0) #for port description
        datapath.send_msg(req)

        req = parser.OFPFlowStatsRequest(datapath) #individual flow statistics
        datapath.send_msg(req)

        req = parser.OFPPortStatsRequest(datapath, 0, ofproto.OFPP_ANY)
        datapath.send_msg(req)

    def install_flow(self, datapaths, link_to_port, path,
                     flow_info, data=None):
        init_time_install = time.time()
        ''' 
            Install flow entires.
            path=[dpid1, dpid2...]
            flow_info=(src_ip, dst_ip)
        '''
        if path is None or len(path) == 0:
            self.logger.info("Path error!")
            return

        in_port = 1
        # changing here
        first_dp = self.datapaths[path[0]]

        out_port = first_dp.ofproto.OFPP_LOCAL
        back_info = (flow_info[1], flow_info[0])

        # Flow installing por middle datapaths in path
        if len(path) > 2:
            for i in range(1, len(path) - 1):
                port = self.get_port_pair_from_link(link_to_port,
                                                    path[i - 1], path[i])
                port_next = self.get_port_pair_from_link(link_to_port,
                                                         path[i], path[i + 1])
                if port and port_next:
                    src_port, dst_port = port[1], port_next[0]
                    # changing here
                    datapath = self.datapaths[path[i]]
                    self.send_flow_mod(datapath, flow_info, src_port, dst_port)
                    self.send_flow_mod(datapath, back_info, dst_port, src_port)
        if len(path) > 1:
            # The last flow entry
            port_pair = self.get_port_pair_from_link(link_to_port,
                                                     path[-2], path[-1])
            if port_pair is None:
                self.logger.info("Port is not found")
                return
            src_port = port_pair[1]
            dst_port = 1  # I know that is the host port
            last_dp = datapaths[path[-1]]
            self.send_flow_mod(last_dp, flow_info, src_port, dst_port)
            self.send_flow_mod(last_dp, back_info, dst_port, src_port)

            # The first flow entry
            port_pair = self.get_port_pair_from_link(link_to_port, path[0], path[1])
            if port_pair is None:
                self.logger.info("Port not found in first hop.")
                return
            out_port = port_pair[0]
            self.send_flow_mod(first_dp, flow_info, in_port, out_port)
            self.send_flow_mod(first_dp, back_info, out_port, in_port)

        # src and dst on the same datapath
        else:
            out_port = 1
            self.send_flow_mod(first_dp, flow_info, in_port, out_port)
            self.send_flow_mod(first_dp, back_info, out_port, in_port)

        end_time_install = time.time()
        total_install = end_time_install - init_time_install

    def send_flow_mod(self, datapath, flow_info, src_port, dst_port):
        """
            Build flow entry, and send it to datapath.
        """
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        actions = []
        actions.append(parser.OFPActionOutput(dst_port)) # Foutre le dawa ici

        match = parser.OFPMatch(
             eth_type=ETH_TYPE_IP, ipv4_src=flow_info[0],
             ipv4_dst=flow_info[1])

        self.add_flow(datapath, 1, match, actions,
                      idle_timeout=250, hard_timeout=0)


    def add_flow(self, dp, priority, match, actions, idle_timeout=0, hard_timeout=0):
        """
            Send a flow entry to datapath.
        """


        ofproto = dp.ofproto
        parser = dp.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=dp, command=dp.ofproto.OFPFC_ADD, priority=priority,
                                idle_timeout=idle_timeout,
                                hard_timeout=hard_timeout,
                                match=match, instructions=inst)
        dp.send_msg(mod)

    def del_flow(self, datapath, dst):
        """
            Deletes a flow entry of the datapath.
        """
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        match = parser.OFPMatch(eth_type=ETH_TYPE_IP, ipv4_src=flow_info[0],ipv4_dst=flow_info[1])
        mod = parser.OFPFlowMod(datapath=datapath, match=match, cookie=0,command=ofproto.OFPFC_DELETE)
        datapath.send_msg(mod)

    def build_packet_out(self, datapath, buffer_id, src_port, dst_port, data):
        """
            Build packet out object.get_RL_paths
        """
        actions = []
        if dst_port:
            actions.append(datapath.ofproto_parser.OFPActionOutput(dst_port))

        msg_data = None
        if buffer_id == datapath.ofproto.OFP_NO_BUFFER:
            if data is None:
                return None
            msg_data = data

        out = datapath.ofproto_parser.OFPPacketOut(
            datapath=datapath, buffer_id=buffer_id,
            data=msg_data, in_port=src_port, actions=actions)
        return out

    def arp_forwarding(self, msg, src_ip, dst_ip):
        """
            Send ARP packet to the destination host if the dst host record
            is existed.
            result = (datapath, port) of host
        """
        datapath = msg.datapath
        ofproto = datapath.ofproto

        result = self.awareness.get_host_location(dst_ip)
        if result:
            # Host has been recorded in access table.
            datapath_dst, out_port = result[0], result[1]
            datapath = self.datapaths[datapath_dst]
            out = self.build_packet_out(datapath, ofproto.OFP_NO_BUFFER,
                                         ofproto.OFPP_CONTROLLER,
                                         out_port, msg.data)
            datapath.send_msg(out)
            self.logger.debug("Deliver ARP packet to knew host")
        else:
            # self.flood(msg)
            pass

    def get_port_pair_from_link(self, link_to_port, src_dpid, dst_dpid):
        """
            Get port pair of link, so that controller can install flow entry.
            link_to_port = {(src_dpid,dst_dpid):(src_port,dst_port),}
        """
        if (src_dpid, dst_dpid) in link_to_port:
            return link_to_port[(src_dpid, dst_dpid)]
        else:
            self.logger.info("Link from dpid:%s to dpid:%s is not in links" %
             (src_dpid, dst_dpid))
            return None

    def get_path(self, src, dst):
        self.paths = None

        if self.paths != None:
            #print ('PATHS: OK')
            path = self.paths.get(src).get(dst)[0]
            return path
        else:
            #print('Getting paths: OK')
            paths = self.get_RL_paths()
            path = paths.get(src).get(dst)[0]
            return path

    def get_RL_paths(self):

        file = '/home/controlador/ryu/ryu/app/SDNapps_proac/paths.json'
        try:
            with open(file,'r') as json_file:
                paths_dict = json.load(json_file)
                paths_dict = ast.literal_eval(json.dumps(paths_dict))
                self.paths = paths_dict
                return self.paths
        except ValueError as e: #error excpetion when trying to read the json and is still been updated
            return
        else:
            with open(file,'r') as json_file: #try again
                paths_dict = json.load(json_file)
                paths_dict = ast.literal_eval(json.dumps(paths_dict))
                self.paths = paths_dict
                return self.paths


#---------------------CONTROL PLANE -----------------------------------------
#-----------------------STATISTICS MODULE FUNCTIONS -------------------------

    def save_stats(self, _dict, key, value, length=5): #Save values in dics (max len 5)
        if key not in _dict:
            _dict[key] = []
        _dict[key].append(value)
        if len(_dict[key]) > length:
            _dict[key].pop(0)

    def get_speed(self, now, pre, period): #bits/s
        if period:
            return ((now - pre)*8) / period
        else:
            return 0

    def get_time(self, sec, nsec): #Total time that the flow was alive in seconds
        return sec + nsec / 1000000000.0

    def get_period(self, n_sec, n_nsec, p_sec, p_nsec): # (time las flow, time)
                                                         # calculates period of time between flows
        return self.get_time(n_sec, n_nsec) - self.get_time(p_sec, p_nsec)

    def get_sw_dst(self, dpid, out_port):
        for key in self.awareness.link_to_port:
            src_port = self.awareness.link_to_port[key][0]
            if key[0] == dpid and src_port == out_port:
                dst_sw = key[1]
                dst_port = self.awareness.link_to_port[key][1]
                return (dst_sw, dst_port)

    def get_link_bw(self, file, src_dpid, dst_dpid):
        fin = open(file, "r")
        bw_capacity_dict = {}
        for line in fin:
            a = line.split(',')
            if a:
                s1 = a[0]
                s2 = a[1]
                # bwd = a[2] #random capacities
                bwd = a[3] #original capacities
                bw_capacity_dict.setdefault(s1,{})
                bw_capacity_dict[str(a[0])][str(a[1])] = bwd
        fin.close()
        bw_link = bw_capacity_dict[str(src_dpid)][str(dst_dpid)]
        return bw_link

    def get_free_bw(self, port_capacity, speed):
        # freebw: Kbit/s
        return max(port_capacity - (speed/ 1000.0), 0)

#------------------MANAGEMENT PLANE MODULE ---------------------------
#------------------PROCESS STATISTICS MODULE FUNCTIONS----------------

    def get_flow_loss(self):
        #Get per flow loss
        bodies = self.stats['flow']
        for dp in bodies.keys():
            list_flows = sorted([flow for flow in bodies[dp] if flow.priority == 1],
                                key=lambda flow: (flow.match.get('ipv4_src'),flow.match.get('ipv4_dst')))
            for stat in list_flows:
                out_port = stat.instructions[0].actions[0].port
                if self.awareness.link_to_port and out_port != 1: #get loss from ports of network
                    key = (stat.match.get('ipv4_src'), stat.match.get('ipv4_dst'))
                    tmp1 = self.flow_stats[dp][key]
                    byte_count_src = tmp1[-1][1]

                    result = self.get_sw_dst(dp, out_port)
                    dst_sw = result[0]
                    tmp2 = self.flow_stats[dst_sw][key]
                    byte_count_dst = tmp2[-1][1]
                    flow_loss = byte_count_src - byte_count_dst
                    self.save_stats(self.flow_loss[dp], key, flow_loss, 5)

    def get_port_loss(self):
        #Get loss_port
        bodies = self.stats['port']
        for dp in sorted(bodies.keys()):
            for stat in sorted(bodies[dp], key=attrgetter('port_no')):
                if self.awareness.link_to_port and stat.port_no != 1 and stat.port_no != ofproto_v1_3.OFPP_LOCAL: #get loss form ports of network
                    key1 = (dp, stat.port_no)
                    tmp1 = self.port_stats[key1]
                    tx_bytes_src = tmp1[-1][0]
                    tx_pkts_src = tmp1[-1][8]

                    key2 = self.get_sw_dst(dp, stat.port_no)
                    tmp2 = self.port_stats[key2]
                    rx_bytes_dst = tmp2[-1][1]
                    rx_pkts_dst = tmp2[-1][9]
                    loss_port = float(tx_pkts_src - rx_pkts_dst) / tx_pkts_src #loss rate
                    values = (loss_port, key2)
                    self.save_stats(self.port_loss[dp], key1, values, 5)

        #Calculates the total link loss and save it in self.link_loss[(node1,node2)]:loss
        for dp in self.port_loss.keys():
            for port in self.port_loss[dp]:
                key2 = self.port_loss[dp][port][-1][1]
                loss_src = self.port_loss[dp][port][-1][0]
                # tx_src = self.port_loss[dp][port][-1][1]
                loss_dst = self.port_loss[key2[0]][key2][-1][0]
                # tx_dst = self.port_loss[key2[0]][key2][-1][1]
                loss_l = (abs(loss_src) + abs(loss_dst)) / 2
                link = (dp, key2[0])
                self.link_loss[link] = loss_l*100.0

    def get_link_free_bw(self):
        #Calculates the total free bw of link and save it in self.link_free_bw[(node1,node2)]:link_free_bw
        for dp in self.free_bandwidth.keys():
            for port in self.free_bandwidth[dp]:
                free_bw1 = self.free_bandwidth[dp][port]
                key2 = self.get_sw_dst(dp, port) #key2 = (dp,port)
                free_bw2= self.free_bandwidth[key2[0]][key2[1]]
                link_free_bw = (free_bw1 + free_bw2)/2
                link = (dp, key2[0])
                self.link_free_bw[link] = link_free_bw

    def get_link_used_bw(self):
        #Calculates the total free bw of link and save it in self.link_free_bw[(node1,node2)]:link_free_bw
        for key in self.port_speed.keys():
            used_bw1 = self.port_speed[key][-1]
            key2 = self.get_sw_dst(key[0], key[1]) #key2 = (dp,port)
            used_bw2 = self.port_speed[key2][-1]
            link_used_bw = (used_bw1 + used_bw2)/2
            link = (key[0], key2[0])
            self.link_used_bw[link] = link_used_bw

    def write_values(self):
        a = time.time()
        if self.delay.link_delay:
            for link in self.link_free_bw:
                self.net_info[link] = [round(self.link_free_bw[link], 6), round(self.delay.link_delay[link], 6),
                                       round(self.link_loss[link], 6)]
                self.net_metrics[link] = [round(self.link_free_bw[link], 6), round(self.link_used_bw[link], 6),
                                          round(self.delay.link_delay[link], 6), round(self.link_loss[link], 6)]

            with open('/home/controlador/ryu/ryu/app/SDNapps_proac/net_info.csv', 'wb') as csvfile:
                header_names = ['node1', 'node2', 'bwd', 'delay', 'pkloss']
                file = csv.writer(csvfile, delimiter=',', quotechar='|', quoting=csv.QUOTE_MINIMAL)
                links_in = []
                file.writerow(header_names)
                for link, values in sorted(self.net_info.items()):
                    links_in.append(link)
                    tup = (link[1], link[0])
                    if tup not in links_in:
                        file.writerow([link[0], link[1], values[0], values[1], values[2]])

            file_metrics = '/home/controlador/ryu/ryu/app/SDNapps_proac/Metrics/' + str(
                self.count_monitor) + '_net_metrics.csv'
            with open(file_metrics, 'wb') as csvfile:
                header_ = ['node1', 'node2', 'free_bw', 'used_bw', 'delay', 'pkloss']
                file = csv.writer(csvfile, delimiter=',', quotechar='|', quoting=csv.QUOTE_MINIMAL)
                links_in = []
                file.writerow(header_)
                for link, values in sorted(self.net_metrics.items()):
                    links_in.append(link)
                    tup = (link[1], link[0])
                    if tup not in links_in:
                        file.writerow([link[0], link[1], values[0], values[1], values[2], values[3]])
            b = time.time()
            return

#---------------------CONTROL PLANE FUNCTIONS---------------------------------
#---------------------STATISTICS MODULE FUNCTIONS ----------------------------

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
     
    def flow_stats_reply_handler(self, ev):
              
        body = ev.msg.body
        dpid = ev.msg.datapath.id
        self.stats['flow'][dpid] = body
        self.flow_stats.setdefault(dpid, {})
        self.flow_speed.setdefault(dpid, {})
        self.flow_loss.setdefault(dpid, {})

        old = np.zeros(shape=(23,23))
        new = np.zeros(shape=(23,23))
        amMap = {"ipv4src" : [] , "ipv4dst" : [] , "byteCount" : []}


        for stat in sorted([flow for flow in body if flow.priority == 1],
                           key=lambda flow: (flow.match.get('ipv4_src'),
                                             flow.match.get('ipv4_dst'))):

            key = (stat.match.get('ipv4_src'), stat.match.get('ipv4_dst'))
            value = (stat.packet_count, stat.byte_count,
                     stat.duration_sec, stat.duration_nsec)#duration_sec: Time flow was alive in seconds
         
            ipv4src = key[0]
            ipv4dst =  key[1]
            packetCount = stat.packet_count
            byteCount= stat.byte_count
            iplsrc = str(ipv4src).strip().split('.')[3]
            ipldst = str(ipv4dst).strip().split('.')[3]
            src = int(iplsrc) - 1
            dst = int(ipldst) - 1
            #print("src: %s, dest: %s, value: %d" %(iplsrc, ipldst, byteCount))
            self.traffic_adj_matrix[src][dst] =  byteCount

        # iterate through the new made up dictionary that has lists of srces , dsts and pcounts 
           
            self.save_stats(self.flow_stats[dpid], key, value, 5)
            pre = 0
            period = setting.MONITOR_PERIOD
            tmp = self.flow_stats[dpid][key]
            if len(tmp) > 1:
                pre = tmp[-2][1] #penultimo flow byte_count
                period = self.get_period(tmp[-1][2], tmp[-1][3], #valores  (sec,nsec) ultimo flow, penultimo flow)
                                          tmp[-2][2], tmp[-2][3])
            speed = self.get_speed(self.flow_stats[dpid][key][-1][1], #ultimo flow byte_count, penultimo byte_count, periodo
                                    pre, period)
            self.save_stats(self.flow_speed[dpid], key, speed, 5) #bits/s
        

        

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def port_stats_reply_handler(self, ev):
        a = time.time()
        body = ev.msg.body
        dpid = ev.msg.datapath.id

        self.stats['port'][dpid] = body
        self.free_bandwidth.setdefault(dpid, {})
        self.port_loss.setdefault(dpid, {})
    

        for stat in sorted(body, key=attrgetter('port_no')):
            port_no = stat.port_no
            key = (dpid, port_no)
            value = (stat.tx_bytes, stat.rx_bytes, stat.rx_errors,
                     stat.duration_sec, stat.duration_nsec, stat.tx_errors, stat.tx_dropped, stat.rx_dropped, stat.tx_packets, stat.rx_packets)
            self.save_stats(self.port_stats, key, value, 5)

            if port_no != ofproto_v1_3.OFPP_LOCAL:
                if port_no != 1 and self.awareness.link_to_port :
                    # Get port speed and Save it.
                    pre = 0
                    period = setting.MONITOR_PERIOD
                    tmp = self.port_stats[key]
                    if len(tmp) > 1:
                        # Calculate with the tx_bytes and rx_bytes
                        pre = tmp[-2][0] + tmp[-2][1] #penultimo port tx_bytes
                        period = self.get_period(tmp[-1][3], tmp[-1][4], tmp[-2][3], tmp[-2][4]) #periodo entre el ultimo y penultimo total bytes en el puerto
                    # print(self.port_stats[key])
                    # print(pre)
                    speed = self.get_speed(self.port_stats[key][-1][0] + self.port_stats[key][-1][1], pre, period) #speed in bits/s
                    self.save_stats(self.port_speed, key, speed, 5)
                    #Get links capacities

                    file = '/home/controlador/ryu/ryu/app/SDNapps_proac/bw_r.txt' # link capacities
                    link_to_port = self.awareness.link_to_port

                    for k in list(link_to_port.keys()):
                        if k[0] == dpid:
                            if link_to_port[k][0] == port_no:
                                dst_dpid = k[1]

                                #FUNCIONA CON LISTA-----------------------------
                                # list_dst_dpid = [k for k in list(link_to_port.keys()) if k[0] == dpid and link_to_port[k][0] == port_no]
                                # if len(list_dst_dpid) > 0:
                                #     dst_dpid = list_dst_dpid[0][1]
                                # -----------------------------------------
                                bw_link = float(self.get_link_bw(file, dpid, dst_dpid))
                                port_state = self.port_features.get(dpid).get(port_no)

                                if port_state:
                                    bw_link_kbps = bw_link * 1000.0
                                    self.port_features[dpid][port_no].append(bw_link_kbps)
                                    free_bw = self.get_free_bw(bw_link_kbps, speed)
                                    self.free_bandwidth[dpid][port_no] = free_bw

    @set_ev_cls(ofp_event.EventOFPPortDescStatsReply, MAIN_DISPATCHER)
    def port_desc_stats_reply_handler(self, ev):
        """
            Save port description info.
        """
        msg = ev.msg
        dpid = msg.datapath.id
        ofproto = msg.datapath.ofproto

        config_dict = {ofproto.OFPPC_PORT_DOWN: "Down",
                       ofproto.OFPPC_NO_RECV: "No Recv",
                       ofproto.OFPPC_NO_FWD: "No Farward",
                       ofproto.OFPPC_NO_PACKET_IN: "No Packet-in"}

        state_dict = {ofproto.OFPPS_LINK_DOWN: "Down",
                      ofproto.OFPPS_BLOCKED: "Blocked",
                      ofproto.OFPPS_LIVE: "Live"}

        ports = []
        for p in ev.msg.body:
            if p.port_no != 1:

                ports.append('port_no=%d hw_addr=%s name=%s config=0x%08x '
                             'state=0x%08x curr=0x%08x advertised=0x%08x '
                             'supported=0x%08x peer=0x%08x curr_speed=%d '
                             'max_speed=%d' %
                             (p.port_no, p.hw_addr,
                              p.name, p.config,
                              p.state, p.curr, p.advertised,
                              p.supported, p.peer, p.curr_speed,
                              p.max_speed))
                if p.config in config_dict:
                    config = config_dict[p.config]
                else:
                    config = "up"

                if p.state in state_dict:
                    state = state_dict[p.state]
                else:
                    state = "up"

                # Recording data.
                port_feature = [config, state]
                self.port_features[dpid][p.port_no] = port_feature

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def port_status_handler(self, ev):
        """
            Handle the port status changed event.
        """
        print("Un port status")
        msg = ev.msg
        ofproto = msg.datapath.ofproto
        reason = msg.reason
        dpid = msg.datapath.id
        port_no = msg.desc.port_no

        reason_dict = {ofproto.OFPPR_ADD: "added",
                       ofproto.OFPPR_DELETE: "deleted",
                       ofproto.OFPPR_MODIFY: "modified", }

        if reason in reason_dict:
            print("switch%d: port %s %s" % (dpid, reason_dict[reason], port_no))
        else:
            print("switch%d: Illegal port state %s %s" % (dpid, port_no, reason))

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        '''
            In packet_in handler, we need to learn access_table by ARP and IP packets.
            Therefore, the first packet from UNKOWN host MUST be ARP
        '''
        msg = ev.msg
        pkt = packet.Packet(msg.data)
        arp_pkt = pkt.get_protocol(arp.arp)
        if isinstance(arp_pkt, arp.arp):
            self.arp_forwarding(msg, arp_pkt.src_ip, arp_pkt.dst_ip)

    def show_stat(self, _type):
        '''
            Show statistics information according to data type.
            _type: 'port' / 'flow'
        '''
        if setting.TOSHOW is False:
            return


        if _type == 'flow' and self.awareness.link_to_port:
            bodies = self.stats['flow']
            print('datapath         ''   ip_src        ip-dst      '
                  'out-port packets  bytes  flow-speed(b/s)')
            print('---------------- ''  -------- ----------------- '
                  '-------- -------- -------- -----------')
            for dpid in bodies.keys():
                for stat in sorted(
                    [flow for flow in bodies[dpid] if flow.priority == 1],
                    key=lambda flow: (flow.match.get('ipv4_src'),
                                      flow.match.get('ipv4_dst'))):
                    key = (stat.match.get('ipv4_src'), stat.match.get('ipv4_dst'))
                    print('{:>016} {:>9} {:>17} {:>8} {:>8} {:>8} {:>8.1f}'.format(
                        dpid,
                        stat.match['ipv4_src'], stat.match['ipv4_dst'], #flow match
                        stat.instructions[0].actions[0].port, #port
                        stat.packet_count, stat.byte_count,
                        abs(self.flow_speed[dpid][key][-1])))
            print()

        if _type == 'port': #and self.awareness.link_to_port:
            bodies = self.stats['port']
            print('\ndatapath  port '
                '   rx-pkts     rx-bytes ''   tx-pkts     tx-bytes '
                ' port-bw(Kb/s)  port-speed(Kb/s)  port-freebw(Kb/s) '
                ' port-state  link-state')
            print('--------  ----  '
                '---------  -----------  ''---------  -----------  '
                '-------------  ---------------  -----------------  '
                '----------  ----------')
            format_ = '{:>8}  {:>4}  {:>9}  {:>11}  {:>9}  {:>11}  {:>13.3f}  {:>15.5f}  {:>17.5f}  {:>10}  {:>10}  {:>10}  {:>10}'


            for dpid in sorted(bodies.keys()):
                for stat in sorted(bodies[dpid], key=attrgetter('port_no')):
                    if stat.port_no != 1:
                        if stat.port_no != ofproto_v1_3.OFPP_LOCAL: #port 1 is the host output
                            if self.free_bandwidth[dpid]:
                                self.logger.info(format_.format(
                                    dpid, stat.port_no, #datapath , num_port
                                    stat.rx_packets, stat.rx_bytes,
                                    stat.tx_packets, stat.tx_bytes,
                                    self.port_features[dpid][stat.port_no][2], #port_bw (kb/s) MAX
                                    abs(self.port_speed[(dpid, stat.port_no)][-1]/1000.0), #port_speed Kbits/s
                                    self.free_bandwidth[dpid][stat.port_no], #port_free bw kb/s
                                    self.port_features[dpid][stat.port_no][0], #port state
                                    self.port_features[dpid][stat.port_no][1], #link state
                                    stat.rx_dropped, stat.tx_dropped))
            print()

        if _type == 'link':
            print('\nnode1  node2  used-bw(Kb/s)   free-bw(Kb/s)    latency(ms)     loss')
            print('-----  -----  --------------   --------------   -----------    ---- ')

            format_ = '{:>5}  {:>5} {:>14.5f}  {:>14.5f}  {:>12}  {:>12}'

            links_in = []
            for link, values in sorted(self.net_info.items()):
                links_in.append(link)
                tup = (link[1], link[0])
                if tup not in links_in:
                    #if (16, 1) in self.net_info:
                #    print("net info 1", self.net_info[16, 1])
                #    print("net info 16", self.net_info[1, 16])
                #    print("values", values)
                    print(format_.format(link[0],link[1],
                        self.link_used_bw[link]/1000.0,
                        values[0], values[1], values[2]))
                    writetoCSV = [link[0],link[1],
                        self.link_used_bw[link]/1000.0,
                        values[0], values[1], values[2]]
                    with open("Metrics.csv", "a") as file:
                        writer = csv.writer(file, quoting = csv.QUOTE_ALL, delimiter = ';')
                        writer.writerows([writetoCSV])
