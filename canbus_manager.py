import socket
import more_itertools as mit
import logging
import time
import re
import yaml
from yamlinclude import YamlIncludeConstructor
import os
import sys
import struct
from datetime import datetime

class canbus_manager:
    #
    # Convert parameters into local variables
    #
    def __init__(self, canbus_ctrl, sensors):
        self.host    = canbus_ctrl['host']
        self.port    = canbus_ctrl['port']
        self.timeout = canbus_ctrl['timeout']
        self.delay   = canbus_ctrl['delay']
        self.sensors = sensors

    # 
    # Send command to socket. 
    #    In case command is empty, it listens to the respose of a previous command
    #    It returns raw ASCII string received
    def send_command(self, client, command, size_rep=80):
        if command != b'':
            client.sendall(command)
        if size_rep:
            data = client.recv(size_rep)
            logging.debug('Received '+repr(data))
            return data.decode('ascii')

    # 
    # It implemets RW access to registers 
    # reg_name: strings indicating register name as a string
    # read : if True it triggers a R access
    # write: if True it triggers a W access
    # write_val: if write is True: it brings the new value to be stored
    # reset: in case it is True, CAN232 controller is reset before accessing to CAN bus
    # 
    def reg_access(self, reg_name, write_val=None, read=True, write=False,reset=True):
        if self.sensors:
            # Create a socket
            client  = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.settimeout(self.timeout)
            try:
                client.connect((self.host, self.port))
                ret_value = {}
                # index= list(mit.locate(self.sensors, pred=lambda d: re.search(reg_name,d["name"])))
                index= list(mit.locate(self.sensors, pred=lambda d: d["name"] == reg_name))
                for idx in index:
                    tx_id = self.sensors[idx]['tx_id']
                    rx_id = self.sensors[idx]['rx_id']
                    reg = self.sensors[idx]['reg']
                    data_type = self.sensors[idx]['data_type']
                    time.sleep(self.delay)
                    data = ""
                    if reset:
                        # Send a request to the host
                        self.send_command(client,b'XX\r',9)
                        while "CAN232" not in data  :
                            data = repr(client.recv(12))
                            logging.debug('Received '+(data))
                        d = self.send_command(client,b'B17\r',4)
                        #time.sleep(0.5)
                        t1 = datetime.now()  

                        while d != '20k\r':
                            time.sleep(0.1)
                            d = self.send_command(client,b'',4)
                            if (datetime.now()-t1).seconds > 5:
                                client.close()
                                raise ValueError
                        # Sets 20kbps as CAN baudrate
                        self.send_command(client,b'Q1,0\r',6)
                    else:
                        # Put CAN232 Offline
                        self.send_command(client,b'F',2)
                    # CAN232 queue #0 configured for Reading 
                    self.send_command(client,b'C0,R,S,7,'+bytes(hex(rx_id), 'utf-8')+b'\r')
                    if write:
                        num_bytes_tx=b'7'
                    else:
                        num_bytes_tx=b'5'
                    # CAN232 queue #1 configured for command to be sent: CAN packet len is 5 or 7 based on if it is a R or W command 
                    self.send_command(client,b'C1,T,S,'+num_bytes_tx+b','+bytes(hex(tx_id), 'utf-8')+b'\r')
                    iid1 = (((rx_id & 0x780) >> 3 ) & 0xf0)
                    if read == True:
                         iid1 += 1
                    id1 = bytes(hex(iid1), 'utf-8')
                    id2 = bytes(hex((rx_id & 7)), 'utf-8')
                    reg_msbyte = bytes(hex((reg>>8)&0xFF), 'utf-8')
                    reg_lsbyte = bytes(hex((reg>>0)&0xFF), 'utf-8')
                    cmd = b'S1,'+id1+b','+id2+b',0xfa,'+reg_msbyte+b','+reg_lsbyte
                    if write == True:
                        if (data_type == 'et_little_endian' or data_type == 'int16' or data_type == 'int'):
                            value = ((write_val&0xFF)<<8)+((write_val&0xFF00)>>8)
                        elif (data_type == 'et_dec_val'):
                            value = int(d*10.)
                        elif (data_type == 'et_cent_val'):
                            value = int(d*100.)
                        elif (data_type == 'et_mil_val'):
                            value = int(d*1000.)
                        else:
                            raise ValueError
                        reg_msbyte = bytes(hex((value>>8)&0xFF), 'utf-8')
                        reg_lsbyte = bytes(hex((value>>0)&0xFF), 'utf-8')
                        cmd += b','+reg_msbyte+b','+reg_lsbyte
                    cmd += b'\r'
                    self.send_command(client,cmd,0)
                    time.sleep(0.1)
                    self.send_command(client,b'',80)
                    # Put CAN 232 Online
                    data = self.send_command(client,b'O',0)
                    time.sleep(0.3)
                    self.send_command(client,b'',2)
                    # Loop for Read or Write: it repeats the command until correctly processed or a timeout is fired
                    repeat = True
                    i = 0
                    t1 = datetime.now()  
                    while repeat:
                        logging.debug('Send command')
                        data = self.send_command(client,b'1',1)
                        while data != '1':
                            if (datetime.now()-t1).seconds > 5:
                                logging.error('Timeout expired')
                                client.close()
                                raise ValueError
                            # Purge receiving path
                            logging.debug('Purging before sending another command')
                            data = self.send_command(client,b'',80)
                            time.sleep(0.1)
                            logging.debug('Send another command')
                            self.send_command(client,b'1',0)
                            data = self.send_command(client,b'',1)
                        # In case of W access nothing is sent back to aknoledge it
                        if write:
                            return 0
                        # Receiving answer: it is a string like this: '(0)  00000301 d2 00 fa 00 11 00 cf'
                        data = self.send_command(client,b'',34)
                        logging.debug('Received ('+str(i)+')  '+(data))
                        data_v = data.split()
                        #
                        # Validate received packet
                        #
                        if len(data_v) != 8:
                            logging.error('Wrong packet len')
                        else:
                            exp_reg = int(data_v[5], base=16)+(int(data_v[4], base=16)<<8)
                            if rx_id != int(data_v[0], base=16):
                                logging.error('Wrong tx_id: expected '+hex(rx_id)+' received '+data_v[0])
                            else:
                                if 'fa' != data_v[3]:
                                    logging.error('Wrong identification char: expected fa received '+data_v[3])
                                else:
                                    if reg != exp_reg and reg != exp_reg+280:
                                        logging.error('Wrong register : expected '+hex(reg)+' or '+hex(reg+280)+' received '+hex(exp_reg))
                                    else:
                                        repeat = False
                        if repeat:
                            time.sleep(2)

                    #
                    # Process received data (16bits)
                    #
                    d = int(data_v[7], base=16)+(int(data_v[6], base=16)<<8)
                    if (data_type == 'et_little_endian' or data_type == 'int16' or data_type == 'int'):
                        value = int(data_v[6], base=16)+(int(data_v[7], base=16)<<8)
                    elif (data_type == 'et_dec_val'):
                        value = float(d)/10.
                    elif (data_type == 'et_cent_val'):
                        value = float(d)/100.
                    elif (data_type == 'et_mil_val'):
                        value = float(d)/1000.
                    else:
                        raise ValueError
                    ret_value['value']  = value
                self.send_command(client,b'F')
                client.close()
                if read:
                    return ret_value
            except OSError as msg:
                 client.close()
                 raise ValueError
        else:
            raise ValueError


if __name__ == '__main__':
    null = None
    true = True
    config_path = os.path.dirname(os.path.realpath(__file__))+'/config'
    config_file = config_path+'/configuration.yaml'
    file_path = os.path.realpath(__file__)
    YamlIncludeConstructor.add_to_loader_class(loader_class=yaml.FullLoader, base_dir=config_path)

    # load configuration file
    with open(config_file, "r") as stream:
        try:
            yaml_str = yaml.load(stream, Loader=yaml.FullLoader)
        except yaml.YAMLError as exc:
            logging.debug('Wrong Yaml File Format')
            sys.exit(0)

    type = 'canbus'
    controller = 'USR232_technicalroom'
    #controller = 'USR232_entrancepanel1'
    device = 'wpc7cool_sensors'
    # device = 'fan1_sensors'
    # device = 'fan2_sensors'
    # device = 'gardenvalves_switches'
    # device = 'heating_switches'
    iterable = yaml_str['canbus']
    index= list(mit.locate(iterable, pred=lambda d: d['name'] == controller))

    controller_dict=yaml_str[type][index[0]]
    registers_dict = yaml_str[type][index[0]][device]
    reg_names=[item['name'] for item in registers_dict]

    # reg = 'total_system_power'
    # reg = 'Switch'
    # reg_names=["Total system power"]
    # reg = 'PROGRAM_SWITCH'
    # reg_names=[reg]
    # logging.getLogger().setLevel(logging.DEBUG)
    FORMAT = ('%(asctime)-15s %(threadName)-15s'
            ' %(levelname)-8s %(module)-15s:%(lineno)-8s %(message)s')
    logging.basicConfig(format=FORMAT)
    log = logging.getLogger()
    
    cbm = canbus_manager(controller_dict,registers_dict)
    print('Type = '+type+' Controller = '+controller+' Device = '+device)
    # reg_names =['Command Request Cold Dehum Recycle']
#    for i in range(0,6):
#    cbm.reg_access(reg,write_val=i,write=True,read=False,reset=True)
    for reg in reg_names:
        val=cbm.reg_access(reg,reset=False)
        print(reg+' = ',str(val['value']))
        #time.sleep(.01)
        # input('Press Enter to continue!')

