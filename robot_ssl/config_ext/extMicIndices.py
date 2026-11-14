"""Microphone indices class definition."""

from typing import Iterable, Tuple, List # for type declaration of variables as a Tuple
import warnings # for raising warnings for less critical issues

class MicIndices:
    """Class managing an instance of a microphone array's indices to the audio channels.
    
    There are three possible known types of channel: 
    * `asr` - channel for automatically recognised speech data (ASR); 
    * `sum` - channel to sum all mic outputs; 
    * `raw` - raw mic channels
    Any other type of channel is considered "unknown" (`unk`).
    """
    
    asr: int | None = None
    sum: int | None = None
    raw: int | Tuple[int, ...] | None = None
    unk: List[int] | None = None
    
    def __init__(self, **kwargs: int | Tuple[int, ...]):
        """Initialise values for the microphone array's indices.

        Returns:
            None.
        """
        indtypes = {"asr":"int","sum":"int","raw":"either"}
        kwargskeys = list(kwargs.keys())
        for indtype in indtypes.keys(): 
            if indtype in kwargs: 
                self.checkargtype(indtype, kwargs[indtype], indtypes[indtype])
                setattr(self, indtype, kwargs[indtype])
                kwargskeys.remove(indtype)
        
        # if sum(i in list(range(2)) for i in indtypes) < len(kwargs): # cool but unnecessary
        if len(kwargskeys) > 0:
            warnings.warn("Extra index types detected - collapsing all to 'unk'")
            self.unk = [item for unkkey in kwargskeys for item in (kwargs[unkkey] if isinstance(kwargs[unkkey], Iterable) else [kwargs[unkkey]])] # type: ignore (Intellisense is just being really dumb here lol)
        return
          
                
    def checkargtype(self, argname, arg, mustbetype: str = "either"):
        """Verify an argument value input follows the necessary rules for its argument.
        
        Parameters:
            * argname : Name of the argument, used for clarity in the error message.
            * arg : The argument value, which is tested against the argument's rules.
            * mustbeint : Flag for whether the argument can be a tuple or whether it must be an int (default is the former - i.e. False).
        
        Raises:
            TypeError: If the argument input does not pass the argument's conditions.

        Returns:
            True, indicating all tests were passed.
        """
        mustbetype = mustbetype.lower()
        if not isinstance(arg, int):
            if mustbetype == "int":
                raise TypeError(f"{argname} is not of a valid type in MicIndices instance - must be int")
            elif not isinstance(arg, tuple):
                raise TypeError(f"{argname} is not of a valid type in MicIndices instance - must be int or tuple")
        elif mustbetype == "tuple":
            raise TypeError(f"{argname} is not of a valid type in MicIndices instance - must be tuple")
        elif not mustbetype in ("int", "tuple", "either"):
            raise ValueError("Parameter 'mustbetype' must be of value 'int', 'tuple' or 'either'")
        
        return True
    
    
    def __str__(self):
        return f"asr: {self.asr}; sum: {self.sum}; raw: {self.raw}; unk: {self.unk}"
    
    
    def _getFlatMicIntList(self):
       return list([x for x in [item for sublist in [self.asr, self.sum, self.raw, self.unk] for item in (sublist if isinstance(sublist, Iterable) else [sublist])] if x is not None])
    
    
    def __len__(self):
        tempflatlist = self._getFlatMicIntList()
        print(tempflatlist)
        #return sum(tempflatlist if any(x is not None for x in tempflatlist) else [0]) # this adds all the mic indices together - not so useful, whoops!
        return len(tempflatlist)
    
    
    def checkMicUniqueness(self):
        uniqueness = True
        uniquemicset = set(self._getFlatMicIntList())
        if uniquemicset is not None and len(uniquemicset) != len(self):
            uniqueness = False
        return uniqueness
    
    
    def checkMicBounds(self, upper):
        boundedness = True
        tempflatlist = self._getFlatMicIntList()
        if any(index < 0 or index >= upper for index in tempflatlist):
            boundedness = False
        return boundedness
    
if __name__ == "__main__":
    # Test script
    testmics = MicIndices(asr=1, sum=2, raw=3, test=(6,7,8,9), testb=10)
    print(testmics.checkMicUniqueness())