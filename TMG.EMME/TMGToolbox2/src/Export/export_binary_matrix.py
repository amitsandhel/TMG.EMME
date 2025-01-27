# ---LICENSE----------------------
"""
    Copyright 2014 Travel Modelling Group, Department of Civil Engineering, University of Toronto

    This file is part of the TMG Toolbox.

    The TMG Toolbox is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    The TMG Toolbox is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with the TMG Toolbox.  If not, see <http://www.gnu.org/licenses/>.
"""
# ---METADATA---------------------
"""
ExportBinaryMatrix

    Authors: pkucirek

    Latest revision by: pkucirek
    
    
    Exports matrix data in the new binary format.
        
"""
# ---VERSION HISTORY
"""
    0.0.1 Created on 2014-06-06 by pkucirek
    
    1.0.0 Published on 2014-06-09
    
    1.0.1 Tool now checks that the matrix exists.
    
"""

import inro.modeller as _m
import traceback as _traceback
from contextlib import contextmanager

# from contextlib import nested

_MODELLER = _m.Modeller()  # Instantiate Modeller once.
_util = _MODELLER.module("tmg2.utilities.general_utilities")
_bank = _MODELLER.emmebank

##########################################################################################################


class ExportBinaryMatrix(_m.Tool()):

    version = "1.0.1"
    tool_run_msg = ""
    number_of_tasks = 1  # For progress reporting, enter the integer number of tasks here

    MATRIX_TYPES = {1: "ms", 2: "mo", 3: "md", 4: "mf"}

    def __init__(self):
        # ---Init internal variables
        self.TRACKER = _util.progress_tracker(self.number_of_tasks)  # init the progress_tracker

        # ---Set the defaults of parameters used by Modeller
        self.Scenario = _MODELLER.scenario  # Default is primary scenario

    ##########################################################################################################
    # ---
    # ---MODELLER INTERACE METHODS

    def page(self):
        return ""

    @_m.method(return_type=_m.TupleType)
    def percent_completed(self):
        return self.TRACKER.get_progress()

    @_m.method(return_type=str)
    def tool_run_msg_status(self):
        return self.tool_run_msg

    @_m.method(return_type=bool)
    def scenario_required(self):
        retval = _util.databankHasDifferentZones(_bank)
        print(retval)
        return retval

    # ---
    # ---XTMF INTERFACE METHODS

    def run_xtmf(self, parameters):
        # xtmf_MatrixType, xtmf_MatrixNumber, ExportFile, xtmf_ScenarioNumber
        xtmf_MatrixType = parameters["matrix_type"]
        xtmf_MatrixNumber = parameters["matrix_number"]
        self.ExportFile = parameters["file_location"]
        xtmf_ScenarioNumber = parameters["scenario_number"]
        if not xtmf_MatrixType in self.MATRIX_TYPES:
            raise IOError(
                "Matrix type '%s' is not recognized. Valid types are " % xtmf_MatrixType
                + "1 for scalar, 2 for origin, 3 for destination, and "
                + "4 for full matrices."
            )

        self.MatrixId = self.MATRIX_TYPES[xtmf_MatrixType] + str(xtmf_MatrixNumber)
        if _bank.matrix(self.MatrixId) == None:
            raise IOError("Matrix %s does not exist." % self.MatrixId)

        if _util.databankHasDifferentZones(_bank):
            self.Scenario = _bank.scenario(xtmf_ScenarioNumber)
            if self.Scenario == None:
                raise Exception(
                    "A valid scenario must be specified as there are "
                    + "multiple zone systems in this Emme project. "
                    + "'%s' is not a valid scenario." % xtmf_ScenarioNumber
                )

        try:
            self._Execute()
        except Exception as e:
            msg = str() + "\n" + _traceback.format_exc()
            raise Exception(msg)

    ##########################################################################################################

    # ---
    # ---MAIN EXECUTION CODE

    def _Execute(self):
        with _m.logbook_trace(
            name="{classname} v{version}".format(classname=(self.__class__.__name__), version=self.version),
            attributes=self._GetAtts(),
        ):

            matrix = _bank.matrix(self.MatrixId)

            if _util.databankHasDifferentZones(_bank):
                data = matrix.get_data(self.Scenario)
            else:
                data = matrix.get_data()

            data.save(self.ExportFile)

            self.TRACKER.complete_task()

    ##########################################################################################################

    # ----Sub functions

    def _GetAtts(self):
        atts = {
            "Matrix": self.MatrixId,
            "Export File": self.ExportFile,
            "Version": self.version,
            "self": self.__MODELLER_NAMESPACE__,
        }

        if _util.databankHasDifferentZones(_bank):
            atts["Scenario"] = self.Scenario

        return atts
