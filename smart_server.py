from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import uvicorn
import yaml, json
import sys
import logging
from mbus_manager import mbus_manager
from canbus_manager import canbus_manager
import more_itertools as mit
from yamlinclude import YamlIncludeConstructor
from kaco_inverter import kaco_inverter
import re
import os

class PostItem(BaseModel):
    value: int

# Logging Management
debug=False
if debug:
    import logging
    FORMAT = ('%(asctime)-15s %(threadName)-15s'
              ' %(levelname)-8s %(module)-15s:%(lineno)-8s %(message)s')
    logging.basicConfig(format=FORMAT)
    log = logging.getLogger()
    log.setLevel(logging.DEBUG)

# instantiate our FastApi application
app = FastAPI()

# Configuration Yaml file management
config_path = os.path.dirname(os.path.realpath(__file__))+'/config'
config_file = config_path+'/configuration.yaml'
file_path = os.path.realpath(__file__)
YamlIncludeConstructor.add_to_loader_class(loader_class=yaml.FullLoader, base_dir=config_path)

# load Yaml file
with open(config_file, "r") as stream:
  try:
    app.config = yaml.load(stream, Loader=yaml.FullLoader)
  except yaml.YAMLError as exc:
    logging.error('Wrong Yaml File Format')
    sys.exit(0)

# create our home page route
@app.get('/')
def root():
  return {'message': 'Hello world'}
  
# API METHODS
# GET
# Read entities configurations by type
@app.get('/config')
def config_detail():
  return app.config

@app.get('/config/{bus_type}')
def config_detail(bus_type: str):
  if bus_type == 'modbus' or bus_type == 'uart':
    return app.config[bus_type]
  else:
    raise HTTPException(status_code=404, detail='Type not known: use either modbus or uart')

# GET
# get register value for a single device/controller
@app.get('/{bus_type}/{controller}/{device}/{reg}')
async def list_items(bus_type: str, controller: str, device: str, reg: str = None):
  try:
    yaml_str = app.config
    iterable = yaml_str[bus_type]
    index= list(mit.locate(iterable, pred=lambda d: d['name'] == controller))
    controller_dict=yaml_str[bus_type][index[0]]
    registers_dict = yaml_str[bus_type][index[0]][device]
    reg_names=[item['name'] for item in registers_dict]
    # filter_list = list(filter(lambda x: re.search(reg, x), reg_names))
    filter_list = list(filter(lambda x: reg == x, reg_names))
    if bus_type == 'modbus':
      bus_mngr = mbus_manager(controller_dict,registers_dict)
      val=[]
      for regs in filter_list:
        dict={}
        dict.update( {'name': regs} )
        dict.update( bus_mngr.reg_access(regs) )
        val.append(dict)
    elif bus_type == 'canbus':
      bus_mngr = canbus_manager(controller_dict,registers_dict)
      val=[]
      for regs in filter_list:
        dict={}
        dict.update( {'name': regs} )
        dict.update( bus_mngr.reg_access(regs) )
        val.append(dict)
    elif bus_type == 'uart':
      if controller_dict['name'] == 'Kaco_attic':
        kaco = kaco_inverter(HOST=controller_dict['host'],PORT=controller_dict['port'],TIMEOUT=controller_dict['timeout'])
        power,volt,temp = kaco.get_inverter_measurements()
        val=[]
        
        for regs in filter_list:
          if regs == 'Power' or regs == 'All':
            dict={'name': 'Power','value': power}
            val.append(dict)
          if regs == 'Volt' or regs == 'All':
            dict={'name': 'Volt','value': volt}
            val.append(dict)
          if regs == 'Temp' or regs == 'All':
            dict={'name': 'Temp','value': temp}
            val.append(dict)
    else:
      raise HTTPException(status_code=404, detail='Type or Controller or device not known')
  except:
    raise HTTPException(status_code=404, detail='General error')
  if val == []:
    raise HTTPException(status_code=404, detail='Register '+reg+' not found')
  else:
    return val
  

# POST
# write register value for a single device/controller
@app.post('/{bus_type}/{controller}/{device}/{reg}')
async def change_items(bus_type: str, controller: str, device: str, reg: str, item: PostItem = None):
  try:
    yaml_str = app.config
    iterable = yaml_str[bus_type]
    index= list(mit.locate(iterable, pred=lambda d: d['name'] == controller))
    controller_dict=yaml_str[bus_type][index[0]]
    registers_dict = yaml_str[bus_type][index[0]][device]
    reg_names=[ritem['name'] for ritem in registers_dict] 
    if bus_type == 'modbus':
      bus_mngr = mbus_manager(controller_dict,registers_dict)
    elif bus_type == 'canbus':
      bus_mngr = canbus_manager(controller_dict,registers_dict)
    else:
      raise HTTPException(status_code=404, detail='bus_type not known')
    val = bus_mngr.reg_access(reg,read=False,write=True,write_val=item.value)
    return val
  except:
    raise HTTPException(status_code=404, detail='Type or Controller or device not known')

  
  
# launch our application with uvicorn
if __name__ == '__main__':
  uvicorn.run(app,host="0.0.0.0",port=8000)
