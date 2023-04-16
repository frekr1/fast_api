import pymodbus.constants
from pymodbus.constants import Endian
from pymodbus.constants import ModbusStatus as ModbusStatus
from pymodbus.client import ModbusTcpClient
from pymodbus.transaction import ModbusRtuFramer as ModbusFramer
# from pymodbus.bit_write_message import _turn_coil_on as on_coil
# from pymodbus.bit_write_message import _turn_coil_off as off_coil
import pymodbus.bit_write_message
from pymodbus.payload import BinaryPayloadDecoder
# from pymodbus.pdu import ModbusExceptions, ModbusRequest, ModbusResponse
from custom_message import CustomModbusResponse, CustomModbusRequest
import more_itertools as mit
import logging
import time
import re
import yaml
from yamlinclude import YamlIncludeConstructor
import os
import sys
import struct
import math

class mbus_manager:
    def __init__(self, mbus_ctrl, sensors):
        self.host = mbus_ctrl['host']
        self.port = mbus_ctrl['port']
        self.timeout = mbus_ctrl['timeout']
        self.delay = mbus_ctrl['delay']
        self.sensors = sensors
 
    def float_regs_validator(self, instance):
        if not instance.isError():
            '''.isError() implemented in pymodbus 1.4.0 and above.'''
            decoder = BinaryPayloadDecoder.fromRegisters(
                instance.registers,
                byteorder=Endian.Big
            )   
            float_val = float(decoder.decode_32bit_float())
            return float_val

        else:
            logging.error("Error in float_regs_validator")
            val = float('nan')
            return val

    def int_regs_validator(self, instance):
        if not instance.isError():
            '''.isError() implemented in pymodbus 1.4.0 and above.'''
            decoder = BinaryPayloadDecoder.fromRegisters(
                instance.registers,
                byteorder=Endian.Big,
                wordorder=Endian.Little
            )   
            val = decoder.decode_16bit_uint()
            return val
        else:
            logging.error("Error in int_regs_validator")
            val = 0xFFFFFFFF
            return val

    def int_coils_validator(self, instance):
        if not instance.isError():
            '''.isError() implemented in pymodbus 1.4.0 and above.'''
            decoder = BinaryPayloadDecoder.fromCoils(
                instance.bits,
                byteorder=Endian.Big,
                wordorder=Endian.Little
            )   
            val = decoder.decode_8bit_uint()
            return val
        else:
            # Error handling.
            logging.error("Error in int_coils_validator")
            val = 0xFFFFFFFF
            return val

    def reg_access(self, reg_name, write_val=None, read=True, write=False):

        if self.sensors:
            success = False
            retry = 0
            while success == False:
               # logging.error("Before Class Inst")
                client = ModbusTcpClient(
                    self.host, 
                    port=self.port,
                    timeout=self.timeout,
                    framer=ModbusFramer)
               # logging.error("Before Connect")
                success = client.connect()
               # logging.error("After Connect")
                if success:
                    client.register(CustomModbusResponse)
                    ret_value = {}
                    # index= list(mit.locate(self.sensors, pred=lambda d: re.search(reg_name,d["name"])))
                    index= list(mit.locate(self.sensors, pred=lambda d: d["name"] == reg_name))
                    for idx in index:
                        addr = self.sensors[idx]['address']
                        slave = self.sensors[idx]['slave']
                        if 'scale' in self.sensors[idx]:
                            scale = self.sensors[idx]['scale']
                        else:
                            scale = 1
                        if 'count' in self.sensors[idx]:
                            count = self.sensors[idx]['count']
                        else:
                            count = 1

                        if 'input_type' in self.sensors[idx]:
                            input_type = self.sensors[idx]['input_type']
                        else:
                            input_type = 'holding'

                        if 'data_type' in self.sensors[idx]:
                            data_type = self.sensors[idx]['data_type']
                        else:
                            data_type = 'int16'

                        if 'bit' in self.sensors[idx]:
                            bit = self.sensors[idx]['bit']
                        else:
                            bit = -1

                        if 'command_on' in self.sensors[idx]:
                            pymodbus.bit_write_message._turn_coil_on = struct.pack(">H",self.sensors[idx]['command_on'])
                        else:
                            pymodbus.bit_write_message._turn_coil_on = struct.pack(">H",ModbusStatus.On)
                        if 'command_off' in self.sensors[idx]:
                            pymodbus.bit_write_message._turn_coil_off = struct.pack(">H",self.sensors[idx]['command_off'])
                        else:
                            pymodbus.bit_write_message._turn_coil_off = struct.pack(">H",ModbusStatus.Off)

                        if 'write_type' in self.sensors[idx]:
                            write_type = self.sensors[idx]['write_type']
                            wr_addr = addr
                            if 'verify' in self.sensors[idx]:
                                input_type = self.sensors[idx]['verify']['input_type']
                                addr = self.sensors[idx]['verify']['address']
                                if 'bit' in self.sensors[idx]['verify']:
                                    bit = self.sensors[idx]['verify']['bit']
                                else:
                                    bit = -1
                                if 'count' in self.sensors[idx]['verify']:
                                    count = self.sensors[idx]['verify']['count']
                                else:
                                    count = 1
                            else:
                                input_type = write_type
                                addr = wr_addr
                        else:
                            write_type = input_type
                            wr_addr =  addr

                        time.sleep(self.delay)
                        if write == True:
                            if write_type == 'coil':
                                request = client.write_coil(address=wr_addr, value = write_val, slave=slave)
                            elif write_type == 'write_register':
                                request = client.write_register(address=wr_addr, value = write_val, slave=slave)
                            else:
                                raise ValueError    
                        if read == True:
                            retry = True
                            while retry:
                                retry = False
                                if input_type == 'coil':
                                    request = client.read_coils(address=addr, count=count, slave=slave)
                                elif input_type == 'holding':
                                    request = client.read_holding_registers(address=addr, count=count, slave=slave)
                                elif input_type == 'input':
                                    request = client.read_input_registers(address=addr, count=count, slave=slave)
                                elif input_type == 'discrete_input':
                                    request = client.read_discrete_inputs(address=addr, count=count, slave=slave)
                                elif input_type == 'fcc_read_version':
                                    request = CustomModbusRequest(unit=slave)
                                    result = client.execute(request)
                                else:
                                    raise ValueError    
                                if data_type == 'float32' or data_type == 'float':
                                    value = self.float_regs_validator(request)
                                    # if not math.isnan(value):
                                    #     retry = True
                                elif (data_type == 'int16' or data_type == 'int') and input_type != 'coil':
                                    value = self.int_regs_validator(request)
                                    if value == 0xFFFFFFFF:
                                        retry = True
                                elif (data_type == 'int16' or data_type == 'int') and input_type == 'coil':
                                    value = self.int_coils_validator(request)
                                    if value == 0xFFFFFFFF:
                                        retry = True
                                elif (data_type == 'int8'):
                                    value = self.int_coils_validator(request)
                                    if value == 0xFFFFFFFF:
                                        retry = True
                                elif (data_type =='string'):
                                    value = result.values.decode("utf-8")
                                else:
                                    raise ValueError
                            if (data_type !='string'):
                                if bit != -1:
                                    value = (value & (1<<bit))>>bit
                                ret_value['value']  = value*scale
                            else:
                                ret_value['value']  = value
                    client.close()
                    if read:
                        return ret_value
                else:
                    client.close()
                    retry +=1
                    logging.error("Connection refused on temptative #"+str(retry))
                    if retry == 5: 
                        success = True
                        logging.error("Aborting: too many trials")
                        raise ValueError
                    else:
                        success = False
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
    logging.getLogger().setLevel(logging.DEBUG)
    #logging.getLogger().setLevel(logging.INFO)
    with open(config_file, "r") as stream:
        try:
            yaml_str = yaml.load(stream, Loader=yaml.FullLoader)
        #    for i in app.config['modbus']:
        #      logging.info(i)
        #    for i in app.config['uart']:
        #      logging.info(i)
        except yaml.YAMLError as exc:
        #    logging.info('Wrong Yaml File Format')
            sys.exit(0)

    type = 'modbus'
    controller = 'Lantronix_garagepanel'
    #controller = 'USR232_entrancepanel1'
    #device = 'smartmeter_sensors'
    #device = 'fan1_sensors'
    #device = 'fan2_sensors'
    #device = 'gardenvalves_switches'
    device = 'heating_switches'
    iterable = yaml_str['modbus']
    index= list(mit.locate(iterable, pred=lambda d: d['name'] == controller))

    controller_dict=yaml_str[type][index[0]]
    registers_dict = yaml_str[type][index[0]][device]
    reg_names=[item['name'] for item in registers_dict]

    # reg = 'total_system_power'
    # reg = 'Switch'
    # reg_names=["Total system power"]
    # reg_names=["Command Status"]
    FORMAT = ('%(asctime)-15s %(threadName)-15s'
            ' %(levelname)-8s %(module)-15s:%(lineno)-8s %(message)s')
    logging.basicConfig(format=FORMAT)
    log = logging.getLogger()
    
    mbm = mbus_manager(controller_dict,registers_dict)
    print('Type = '+type+' Controller = '+controller+' Device = '+device)
    # reg_names =['Command Request Cold Dehum Recycle']
    for reg in reg_names:
        if "Switch" in reg:
            write_val=0
            # else:
            #     write_val=0
        #     if "Dehum" in reg:
        #         write_val += (1<<5)
        #     if "Renew" in reg:
        #         write_val += (1<<3)
        #     if "Warm" in reg:
        #         write_val += (1<<9)
        #     if "Cold" in reg:
        #         write_val += (1<<1)+(1<<2)
        #     log.setLevel(logging.DEBUG)
            mbm.reg_access(reg,write_val=write_val,read=False, write=True)  
        #     log.setLevel(logging.INFO)
        #     time.sleep(.01)
        #     val=mbm.reg_access(reg)
        #     print(reg+' = ',str(val['value']))
            time.sleep(.1)
        #     write_val=0
        #     mbm.reg_access(reg,write_val=write_val,read=False, write=True)     
        #     time.sleep(.01)
        if reg in reg:
            val=mbm.reg_access(reg)
            print(reg+' = ',str(val['value']))
        time.sleep(.1)
        input("Press key to continue")
