"""Replaceable robot head/camera control interface (console and HTTP adapters)."""

import json
import logging
import math
import time
import socket


class RobotMovementInterface:
    """Class for managing computer-to-robot interaction.
    
    Currently controls robot rotation and alertness.  Note that socket must be closed after completion of use."""
    
    _alertState = False
    
    # Alertness state property - controls sending of alertness data while flag is set.
    @property
    def alertState(self):
        return self._alertState
    
    @alertState.setter
    def alertState(self, value: bool):
        if isinstance(value, bool):
            self._alertState = value
            
            self.socket.sendall(b'%a\n' % json.dumps({"alertness": value}))
            #logging.info("[ROBOT ALERTNESS] %s", ("Alertness is high" if value else "Alertness is low"))
        else:
            raise TypeError("Alertness state must be a boolean")
        return
    
    def __init__(self, host: str="127.0.0.1", port: int=5000) -> None:
        """Turn the robot's head by a specific rotation.
                
        Parameters:
            * host : Host domain through which the socket must connect to access the robot.
            * port : Port through which the socket must connect on the host to access the robot.

        Returns:
            None.
        """
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((host, port))
        logging.info("[ROBOT] Socket connection set up.  Ready to take robot data.")
        
        return

    def turnBy(self, degrees: float, details: str) -> bool:
        """Turn the robot's head by a specific rotation.
        
        Parameters:
            * degrees : Target rotation relative to the current rotation, where 0° is forward and positive is clockwise.
            * details : Details for the alertness state setting (e.g. reason for robot alertness); defaults to an empty string, which leaves out that section from the log entry entirely.

        Returns:
            `True` if packet is successfully sent.
        
        Notes:
            Sends json data to port localhost:5000 controlling the 'turnby' parameter, with *negative* being clockwise to match ROS 2 specifications.
        """
        self.socket.sendall(b'%a\n' % json.dumps({"turnby": -degrees}))
        
        logging.info(
            "[ROBOT] Turning by %+.1f° %s%s", abs(degrees), ("left" if math.copysign(1, degrees) > 0 else "right"), (f" ({details})" if details else "")
        )
        
        time.sleep(0.1)
        
        return True
    
    def setAlertness(self, value: bool, details: str="") -> bool:
        """Set the alertness of the robot.
        
        Parameters:
            * value : Flag for whether the robot should be alert (True = yes).
            * details : Details for the alertness state setting (e.g. reason for robot alertness); defaults to an empty string, which leaves out that section from the log entry entirely.

        Returns:
            `True` if alertness is successfully set.
        
        Notes:
            Sends json data to port localhost:5000 controlling the 'alertness' parameter, with `True` being alert.
        """
        self.alertState = value
        logging.info("[ROBOT ALERTNESS] %s%s", ("Alertness is high" if value else "Alertness is low"), (f" ({details})" if details else ""))
        return True
    
    def close(self) -> bool:
        """Close the socket connecting to the robot.

        Returns:
            `True` if socket is successfully closed.
        """
        self.socket.close()
        return True