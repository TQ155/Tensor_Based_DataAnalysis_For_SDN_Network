#!/usr/bin/python
import os
import time
import random
from random import randint
import xml.etree.ElementTree as et
import glob

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.log import setLogLevel, info
from mininet.cli import CLI
from mininet.node import Host
from mininet.link import TCLink, Link
from mininet.node import RemoteController, OVSSwitch


class Project(Topo):
    def __init__(self):
        # Initialize topology
        Topo.__init__(self)

        # Add hosts
        h1 = self.addHost('h1', ip='10.0.0.1/24')
        h2 = self.addHost('h2', ip='10.0.0.2/24')
        h3 = self.addHost('h3', ip='10.0.0.3/24')
        h4 = self.addHost('h4', ip='10.0.0.4/24')
        h5 = self.addHost('h5', ip='10.0.0.5/24')
        h6 = self.addHost('h6', ip='10.0.0.6/24')
        h7 = self.addHost('h7', ip='10.0.0.7/24')
        h8 = self.addHost('h8', ip='10.0.0.8/24')
        h9 = self.addHost('h9', ip='10.0.0.9/24')
        h10 = self.addHost('h10', ip='10.0.0.10/24')
        h11 = self.addHost('h11', ip='10.0.0.11/24')
        h12 = self.addHost('h12', ip='10.0.0.12/24')
        h13 = self.addHost('h13', ip='10.0.0.13/24')
        h14 = self.addHost('h14', ip='10.0.0.14/24')
        h15 = self.addHost('h15', ip='10.0.0.15/24')
        h16 = self.addHost('h16', ip='10.0.0.16/24')
        h17 = self.addHost('h17', ip='10.0.0.17/24')
        h18 = self.addHost('h18', ip='10.0.0.18/24')
        h19 = self.addHost('h19', ip='10.0.0.19/24')
        h20 = self.addHost('h20', ip='10.0.0.20/24')
        h21 = self.addHost('h21', ip='10.0.0.21/24')
        h22 = self.addHost('h22', ip='10.0.0.22/24')
        h23 = self.addHost('h23', ip='10.0.0.23/24')

        # Add switches
        s1 = self.addSwitch('s1')
        s2 = self.addSwitch('s2')
        s3 = self.addSwitch('s3')
        s4 = self.addSwitch('s4')
        s5 = self.addSwitch('s5')
        s6 = self.addSwitch('s6')
        s7 = self.addSwitch('s7')
        s8 = self.addSwitch('s8')
        s9 = self.addSwitch('s9')
        s10 = self.addSwitch('s10')
        s11 = self.addSwitch('s11')
        s12 = self.addSwitch('s12')
        s13 = self.addSwitch('s13')
        s14 = self.addSwitch('s14')
        s15 = self.addSwitch('s15')
        s16 = self.addSwitch('s16')
        s17 = self.addSwitch('s17')
        s18 = self.addSwitch('s18')
        s19 = self.addSwitch('s19')
        s20 = self.addSwitch('s20')
        s21 = self.addSwitch('s21')
        s22 = self.addSwitch('s22')
        s23 = self.addSwitch('s23')

        # Add links
        self.addLink(h1, s1, cls=TCLink)
        self.addLink(h2, s2, cls=TCLink)
        self.addLink(h3, s3, cls=TCLink)
        self.addLink(h4, s4, cls=TCLink)
        self.addLink(h5, s5, cls=TCLink)
        self.addLink(h6, s6, cls=TCLink)
        self.addLink(h7, s7, cls=TCLink)
        self.addLink(h8, s8, cls=TCLink)
        self.addLink(h9, s9, cls=TCLink)
        self.addLink(h10,s10, cls=TCLink)
        self.addLink(h11,s11, cls=TCLink)
        self.addLink(h12,s12, cls=TCLink)
        self.addLink(h13,s13, cls=TCLink)
        self.addLink(h14,s14, cls=TCLink)
        self.addLink(h15,s15, cls=TCLink)
        self.addLink(h16,s16, cls=TCLink)
        self.addLink(h17,s17, cls=TCLink)
        self.addLink(h18,s18, cls=TCLink)
        self.addLink(h19,s19, cls=TCLink)
        self.addLink(h20,s20, cls=TCLink)
        self.addLink(h21,s21, cls=TCLink)
        self.addLink(h22,s22, cls=TCLink)
        self.addLink(h23,s23, cls=TCLink)

        self.addLink(s1, s3, cls=TCLink, params1 = {'bw':10}, params2 = {'bw':10})
        self.addLink(s1, s7, cls=TCLink, params1 = {'bw':10}, params2 = {'bw':10})
        self.addLink(s1, s16, cls=TCLink, params1 = {'bw':10}, params2 = {'bw':10})
        
        self.addLink(s2, s4, cls=TCLink, params1 = {'bw':10}, params2 = {'bw':10})
        self.addLink(s2, s7, cls=TCLink, params1 = {'bw':10}, params2 = {'bw':10})
        self.addLink(s2, s12, cls=TCLink, params1 = {'bw':10}, params2 = {'bw':10})
        self.addLink(s2, s13, cls=TCLink, params1 = {'bw':10}, params2 = {'bw':10})
        self.addLink(s2, s18, cls=TCLink, params1 = {'bw':2.5}, params2 = {'bw':2.5})
        self.addLink(s2, s23, cls=TCLink, params1 = {'bw':2.5}, params2 = {'bw':2.5})
        
        self.addLink(s3, s10, cls=TCLink, params1 = {'bw':10}, params2 = {'bw':10})
        self.addLink(s3, s11, cls=TCLink, params1 = {'bw':2.5}, params2 = {'bw':2.5})
        self.addLink(s3, s14, cls=TCLink, params1 = {'bw':0.155}, params2 = {'bw':0.155})
        self.addLink(s3, s21, cls=TCLink, params1 = {'bw':10}, params2 = {'bw':10})
        
        self.addLink(s4, s16, cls=TCLink, params1 = {'bw':10}, params2 = {'bw':10})

        self.addLink(s5, s8, cls=TCLink, params1 = {'bw':2.5}, params2 = {'bw':2.5})
        self.addLink(s5, s16, cls=TCLink, params1 = {'bw':2.5}, params2 = {'bw':2.5})

        self.addLink(s6, s7, cls=TCLink, params1 = {'bw':0.155}, params2 = {'bw':0.155})
        self.addLink(s6, s19, cls=TCLink, params1 = {'bw':0.155}, params2 = {'bw':0.155})

        self.addLink(s7, s17, cls=TCLink, params1 = {'bw':10}, params2 = {'bw':10})
        self.addLink(s7, s19, cls=TCLink, params1 = {'bw':2.5}, params2 = {'bw':2.5})
        self.addLink(s7, s21, cls=TCLink, params1 = {'bw':10}, params2 = {'bw':10})

        self.addLink(s8, s9, cls=TCLink, params1 = {'bw':2.5}, params2 = {'bw':2.5})

        self.addLink(s9, s15, cls=TCLink, params1 = {'bw':2.5}, params2 = {'bw':2.5})
        self.addLink(s9, s16, cls=TCLink, params1 = {'bw':10}, params2 = {'bw':10})

        self.addLink(s10, s11, cls=TCLink, params1 = {'bw':2.5}, params2 = {'bw':2.5})
        self.addLink(s10, s12, cls=TCLink, params1 = {'bw':10}, params2 = {'bw':10})
        self.addLink(s10, s16, cls=TCLink, params1 = {'bw':10}, params2 = {'bw':10})
        self.addLink(s10, s17, cls=TCLink, params1 = {'bw':10}, params2 = {'bw':10})

        self.addLink(s12, s22, cls=TCLink, params1 = {'bw':10}, params2 = {'bw':10})

        self.addLink(s13, s14, cls=TCLink, params1 = {'bw':0.155}, params2 = {'bw':0.155})
        self.addLink(s13, s17, cls=TCLink, params1 = {'bw':10}, params2 = {'bw':10})
        self.addLink(s13, s19, cls=TCLink, params1 = {'bw':2.5}, params2 = {'bw':2.5})

        self.addLink(s15, s20, cls=TCLink, params1 = {'bw':2.5}, params2 = {'bw':2.5})

        self.addLink(s17, s20, cls=TCLink, params1 = {'bw':10}, params2 = {'bw':10})
        self.addLink(s17, s23, cls=TCLink, params1 = {'bw':2.5}, params2 = {'bw':2.5})

        self.addLink(s18, s21, cls=TCLink, params1 = {'bw':2.5}, params2 = {'bw':2.5})

        self.addLink(s20, s22, cls=TCLink, params1 = {'bw':2.5}, params2 = {'bw':2.5})


def run():
    topo = Project()
    net = Mininet(
        topo=topo,
        controller=RemoteController('c0', ip='127.0.0.1', port=6633, protocols="OpenFlow13"),
        switch=OVSSwitch)
    net.start()
    time.sleep(20)

    # Learning phase of the positions of each IP for the controller

    net.get('h1').cmd("ping -c 1 10.0.0.2")
    
    	############################## Check Connectivity from all hosts to h1

    for hostSrc in ['h2', 'h3', 'h4', 'h5', 'h6', 'h7', 'h8', 'h9', 'h10', 'h11', 'h12', 'h13', 'h14', 'h15', 'h16', 'h17', 'h18', 'h19', 'h20', 'h21', 'h22', 'h23']:
        hostDst = random.choice(['1'])
        net.get(hostSrc).cmd("ping -c 1 10.0.0." + hostDst)
        
        ############################## 

    for hostSrc in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'h7', 'h8', 'h9', 'h10', 'h11', 'h12', 'h13', 'h14', 'h15', 'h16', 'h17', 'h18', 'h19', 'h20', 'h21', 'h22', 'h23']:
        for hostDst in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'h7', 'h8', 'h9', 'h10', 'h11', 'h12', 'h13', 'h14', 'h15', 'h16', 'h17', 'h18', 'h19', 'h20', 'h21', 'h22', 'h23']:
            # How does iperf work? 
            print("iperf  -s -p " + hostDst[1:] + '00' + hostSrc[1:] + " &")
            net.get(hostSrc).cmd("iperf -s -p " + hostDst[1:] + '00' + hostSrc[1:] + " &")
            # h1 -> iperf -s -p 
    time.sleep(30)

    
    path_to_target = './Month2/'
    path_to_file_list = glob.glob(path_to_target + '*xml' )
    path_to_file_list.sort()
 
    # while True:
    for filename in path_to_file_list:
        
        my_tree = et.parse(filename)
        my_root = my_tree.getroot()

        for j in range (len(my_root[1])):
            hostSrc = 'h' + str(my_root[1][j].attrib['id'])
            
            for i in range(len(my_root[1][j])):
                
                frequencekbps = float(my_root[1][j][i].text) 
                hostDst = str(my_root[1][j][i].attrib['id'])
                nbrByte = frequencekbps * 15 * 60 * 1000
                longInterA = str(nbrByte)
                tempsTransmission = 15 #60*60
                
                print("On transmet src ", hostSrc)
                print("On transmet dst ", hostDst)
                print("On transmet ", frequencekbps)
                print("The file : ", filename)
                # How does this line work? 
                print("L'iperf ","iperf  -c 10.0.0." + hostDst + " -p " + hostSrc[1:] + '00' + hostDst + " -u -b " + str(format(float(frequencekbps),'.3f')) + " -w 256 -t " + str(tempsTransmission) + " &")
                net.get(hostSrc).cmd("iperf  -c 10.0.0." + hostDst + " -p " + hostSrc[1:] + '00' + hostDst + " -u -b " + str(format(float(frequencekbps),'.3f')) + " -w 256 -t " + str(tempsTransmission) + " &")
        time.sleep(15) #60*60
        # break
        # break
        print("On change")

    net.stop()


if __name__ == '__main__':
    setLogLevel('info')
    run()
