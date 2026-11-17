"""Replaceable robot head/camera control interface (console and HTTP adapters)."""

import json
import logging
import math
import time
import socket
from typing import Any, Dict


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
            
            if self.socket is None: self.socket = self.tryConnection()
            self._tryToSendData({"alertness": value})
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
        self.host_address = (host, port)
        self.socket = self.tryConnection()
        if self.socket is not None:
            logging.info("[ROBOT] Ready to take robot data.")
        else:
            logging.info("[ROBOT] Connection details are set but nothing is currently available to listen to the port.  Will continue testing to connect when a listener is found...")
        
        return
    
    def tryConnection(self, setup=False) -> socket.socket | None:
        socket_data: socket.socket | None = None
        try:
            socket_data = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            print(self.host_address)
            socket_data.connect(self.host_address)
        except ConnectionRefusedError:
            socket_data = None
        else:
            if setup: logging.info("[ROBOT] Socket connection set up.")
            else: logging.info("[ROBOT] Listener found; socket connection established.")
        
        return socket_data

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
        if self.socket is None: 
            self.socket = self.tryConnection()
        self._tryToSendData({"turnby": -degrees})
        
        if self.socket is not None:
            logging.info(
                "[ROBOT] Turning by %+.1f° %s%s", abs(degrees), ("left" if math.copysign(1, degrees) > 0 else "right"), (f" ({details})" if details else "")
            )
        else:
            logging.info("[ROBOT] Nothing to turn - nothing is listening to the port.  Will continue trying connection...")
            logging.info(
                "[ROBOT] Would-be turn factor: %+.1f° %s%s", abs(degrees), ("left" if math.copysign(1, degrees) > 0 else "right"), (f" ({details})" if details else "")
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
        if self.socket is not None:
            logging.info("[ROBOT] %s%s", ("Alertness is high" if value else "Alertness is low"), (f" ({details})" if details else ""))
        else:
            logging.info("[ROBOT] Nothing to alert - nothing is listening to the port.  Will continue trying connection...")
            logging.info("[ROBOT] Would be alertness: %s%s", ("Alertness is high" if value else "Alertness is low"), (f" ({details})" if details else ""))
        return True
    
    def _tryToSendData(self, eventData: Dict[str, Any]) -> bool:
        data_sent = False
        if self.socket is not None:
            try:
                self.socket.sendall(json.dumps(eventData).encode())
            except BrokenPipeError:
                logging.info("[ROBOT] Listener no longer available; socket connection terminated.")
                self.socket = None
            else:
                data_sent = True
        return data_sent
    
    def close(self) -> bool:
        """Close the socket connecting to the robot.
        
        (NOTE: Only one side of the port should close the connection.  In our case, the server is closing the connection, which means the sender does not need to close the port.)

        Returns:
            `True` ~~if socket is successfully closed.~~
        """
        # self.socket.close()
        return True