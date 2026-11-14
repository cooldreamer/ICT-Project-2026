"""Test file for communication with the reSpeaker XVF3800 microphone array using libusb/pyusb."""

import struct # for neat structuring of binary data
import time # for delaying the main loop (just time.sleep())
import traceback # for printing the full traceback of exceptions

 # for the efficient and safe handling of USB device connections
import libusb_package # Windows (a wrapper for libusb, a C library that provides generic access to USB devices)
import usb # Mac/Linux (pyusb, a Python library that provides easy access to USB devices)

# Project config settings (for microphone array, etc.)
# If the script is run directly, it cannot natively access the config module; adjustment to the import path is needed to include the parent directory
# (Note: Since this is a test script using an alternative method for reading the microphone array, we do not want to import the full robot app module)
if not __name__.startswith("robotssl"):
    if __name__ == "__main__":
        import sys
        from pathlib import Path

        # Get the absolute path of the directory two levels up
        parent_dir = Path(__file__).resolve().parent.parent

        # Add it to the path
        sys.path.insert(0, str(parent_dir))

    # Now import normally
    from config import AppConfig 
else:
    from robot_ssl.config import AppConfig

PARAMETERS = {
    "VERSION": (48, 0, 3, "ro", "uint8"),
    "AEC_AZIMUTH_VALUES": (33, 75, 16, "ro", "radians"),
    "DOA_VALUE": (20, 18, 4, "ro", "uint16"),
    "REBOOT": (48, 7, 1, "wo", "uint8")
}

# Adapted from the official reSpeaker Wiki (https://wiki.seeedstudio.com/respeaker_xvf3800_python_sdk/)
class reSpeaker:
    """Read or write XVF3800 control parameters over USB vendor transfers."""

    TIMEOUT = 10_000 # USB timeout - 10 seconds
    
    def __init__(self, dev, config: AppConfig):
        """Wrap an already-discovered USB device and its application config.

        Parameters:
            * dev : Discovered USB device object.
            * config : Application configuration associated with the device.

        Returns:
            None.
        """
        self.dev = dev
        self.config = config
        
        # self.device = None
        # self.interface = None
        # self.endpoint_in = None
        # self.endpoint_out = None
        
        # self.open_device()
        return
    
    def write(self, name, data_list):
        """Write a supported writable parameter using its configured encoding.

        Parameters:
            * name : Name of the USB control parameter.
            * data_list : Values to encode and send.

        Raises:
            ValueError: If the parameter is read-only or the value count does
                not match its specification.

        Returns:
            None.
        """
        if name in PARAMETERS:
            data = PARAMETERS[name]
        
            if data[3] == "ro":
                raise ValueError(f"Parameter {name} is read-only")
            
            if len(data_list) != data[2]:
                raise ValueError(f"Parameter {name} expects {data[2]} values, got {len(data_list)}")
            
            windex = data[0]
            wvalue = data[1]
            data_type = data[4]
            data_cnt = data[2]
            payload = []
            
            if data_type in ('float', 'radians'):
                payload = [struct.pack(b'f', float(value)) for value in data_list[:data_cnt]]
            elif data_type in ('char', 'uint8'):
                payload = [value.to_bytes(1, byteorder='little') for value in data_list[:data_cnt]]
            else:
                payload = [struct.pack(b'i', value) for value in data_list[:data_cnt]]
            
            print(f"WriteCMD {name}: cmdid={wvalue}, resid={windex}, payload={payload}")
            self.dev.ctrl_transfer(usb.util.CTRL_OUT | usb.util.CTRL_TYPE_VENDOR | usb.util.CTRL_RECIPIENT_DEVICE, 0, wvalue, windex, payload, timeout=self.TIMEOUT)
        
        return
    
    def read(self, name):
        """Read a supported parameter and decode its response values.

        Parameters:
            * name : Name of the USB control parameter.

        Notes:
            The device documentation does not clearly specify write-only
            parameter read behavior, so this method does not reject those
            reads in advance.

        Returns:
            A list of decoded values for a supported parameter, or ``None`` if
            the parameter name is unknown.
        """
        result = None
        
        if name in PARAMETERS:
            data = PARAMETERS[name]
            
            # Presumably correct, although the Wiki neglects this
            # if data[3] == "wo":
            #     raise ValueError(f"Parameter {name} is write-only")
            
            resid = data[0]
            cmdid = 0x80 | data[1]
            length = data[2] + 1
            
            # print may slow down the USB transfer, so it's commented out for now
            # print(f"ReadCMD {name}: cmdid={cmdid}, resid={resid}, payload_len={length}")
            
            response = self.dev.ctrl_transfer(usb.util.CTRL_IN | usb.util.CTRL_TYPE_VENDOR | usb.util.CTRL_RECIPIENT_DEVICE, 0, cmdid, resid, length, timeout=self.TIMEOUT)
            
            byte_data = response.tobytes()
            
            if data[4] == 'uint8':
                result = response.tolist()
            elif data[4] == 'radians':
                num_floats = (length - 1) // 4
                fmt = '<' + 'f' * num_floats
                result = list(struct.unpack(fmt, byte_data[1:1 + num_floats * 4]))
            elif data[4] == 'uint16':
                num_words = data[2] // 2
                fmt = '<' + 'H' * num_words
                result = list(struct.unpack(fmt, byte_data[1:1 + num_words * 2]))
        
        return result
    
    def close(self):
        """Release resources associated with the USB device.

        Returns:
            None.
        """
        usb.util.dispose_resources(self.dev)
        return

def find(vid=0x2886, pid=0x001A):
    """Find the XVF3800 by USB vendor/product ID.

    Parameters:
        * vid : USB vendor ID for which to search (defaults to manufacturer-spec'd vendor ID).
        * pid : USB product ID for which to search (defaults to manufacturer-spec'd product ID).

    Returns:
        A wrapper around the discovered USB device.

    Raises:
        RuntimeError: If no matching USB device is found.
    """
    if sys.platform.startswith("win"):
        dev = libusb_package.find(idVendor=vid, idProduct=pid)
    else:
        dev = usb.core.find(idVendor=vid, idProduct=pid)
    if not dev:
        raise RuntimeError("Device not found")
    #print(dev.is_kernel_driver_active(0))
    # if dev.is_kernel_driver_active(0):
    #     dev.detach_kernel_driver(0)
    # usb.util.claim_interface(dev, 0)
    return reSpeaker(dev, AppConfig())

def main():
    """Read and print microphone firmware and direction-of-arrival values.

    Returns:
        None.
    """
    try:
        dev = find()
        print("Device found" if dev else "No device found")
        
        print(f"VERSION: {dev.read('VERSION')}")
        
        try:
            while True:
                result = dev.read("DOA_VALUE")
                doa_angle = result[0] if result else None
                speech_active = result[1] if result and len(result) > 1 else None
                
                print(f"SPEECH_DETECTED: {speech_active}, DOA_VALUE: {doa_angle}")
                
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("Interrupt - closing naturally...")
        except Exception as e:
            print(f"Error: {e}")
            print(traceback.format_exc())
        finally:
            if 'dev' in locals():
                dev.close()
                print("Device closed")
    except Exception as e:
        print(f"Error: {e}")
        print(traceback.format_exc())
    finally:
        dev.close() if 'dev' in locals() and type(dev).__name__ == 'reSpeaker' else None
        
if __name__ == "__main__":
    main()