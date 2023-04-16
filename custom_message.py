import struct

from pymodbus.client import ModbusTcpClient as ModbusClient
from pymodbus.transaction import ModbusRtuFramer as ModbusFramer
from pymodbus.pdu import ModbusRequest, ModbusResponse








class CustomModbusResponse(ModbusResponse):
    """Custom modbus response."""

    function_code = 100
    _rtu_frame_size = 20

    def __init__(self, values=None, **kwargs):
        """Initialize."""
        ModbusResponse.__init__(self, **kwargs)

    def decode(self, data):
        """Decode response pdu

        :param data: The packet data to decode
        """
        self.values = data

class CustomModbusRequest(ModbusRequest):
    """Custom modbus request."""

    function_code = 100
    _rtu_frame_size = 20

    def __init__(self, **kwargs):
        """Initialize."""
        ModbusRequest.__init__(self, **kwargs)

    def encode(self):
        """Encode."""
        return struct.pack("")

    def get_response_pdu_size(self):
        return self._rtu_frame_size-3 # excluding CRC and 1st byte (address)



# --------------------------------------------------------------------------- #
# execute the request with your client
# --------------------------------------------------------------------------- #
# using the with context, the client will automatically be connected
# and closed when it leaves the current scope.
# --------------------------------------------------------------------------- #


if __name__ == "__main__":

    import logging
    debug=False

    if debug:
        import logging
        FORMAT = ('%(asctime)-15s %(threadName)-15s'
                ' %(levelname)-8s %(module)-15s:%(lineno)-8s %(message)s')
        logging.basicConfig(format=FORMAT)
        log = logging.getLogger()
        log.setLevel(logging.DEBUG)

    with ModbusClient(host='192.168.1.241', port=10002, framer=ModbusFramer) as client:
        client.register(CustomModbusResponse)
        request = CustomModbusRequest(unit=65)
        result = client.execute(request)
        print(result.values.decode("utf-8"))