"""
    Copyright 2022 Travel Modelling Group, Department of Civil Engineering, University of Toronto

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
[TITLE]

    Authors: pkucirek

    Latest revision by: pkucirek
    
    
    [Description]
        
"""
# ---VERSION HISTORY
"""
    0.0.1 Created on 2014-08-28 by pkucirek
    
    1.0.0 Published on 2014-08-28

    2.0.0 Refactored & updated for XTMF2/TMGToolbox2 on 2021-10-20 by Williams Diogu
    
"""
import traceback as _traceback
import inro.modeller as _m

_m.InstanceType = object
_m.TupleType = object

_MODELLER = _m.Modeller()  # Instantiate Modeller once.
_util = _MODELLER.module("tmg2.utilities.general_utilities")
_tmgTPB = _MODELLER.module("tmg2.utilities.TMG_tool_page_builder")

##########################################################################################################


class ReverseTransitLines(_m.Tool()):

    version = "1.0.0"
    tool_run_msg = ""
    number_of_tasks = 1  # For progress reporting, enter the integer number of tasks here

    # ---PARAMETERS

    scenario = _m.Attribute(_m.InstanceType)  # common variable or parameter
    line_selector_expression = _m.Attribute(str)

    def __init__(self):
        # ---Init internal variables
        self.TRACKER = _util.progress_tracker(self.number_of_tasks)  # init the progress_tracker

        # ---Set the defaults of parameters used by Modeller
        self.scenario = _MODELLER.scenario  # Default is primary scenario
        self.line_selector_expression = "mode=r"

    def page(self):
        pb = _tmgTPB.TmgToolPageBuilder(
            self,
            title="Reverse Transit Lines v%s" % self.version,
            description="Reverses the itineraries of a subset of transit lines. It will \
                         try to preserve the line ID of the original line by appending or \
                         modifying the final character. Reports to the Logbook which new lines \
                         are reversed copies of which other lines.",
            branding_text="- TMG Toolbox",
        )

        if self.tool_run_msg != "":  # to display messages in the page
            pb.tool_run_status(self.tool_run_msg_status)

        pb.add_select_scenario(tool_attribute_name="Scenario", title="Scenario:", allow_none=False)

        pb.add_text_box(
            tool_attribute_name="line_selector_expression",
            size=100,
            multi_line=True,
            title="Line selector expression",
            note="Write a network calculator expression to select lines to reverse.",
        )

        return pb.render()

    def run(self):
        self.tool_run_msg = ""
        self.TRACKER.reset()

        try:
            self._execute()
        except Exception as e:
            self.tool_run_msg = _m.PageBuilder.format_exception(e, _traceback.format_exc())
            raise

        self.tool_run_msg = _m.PageBuilder.format_info("Done.")

    def run_xtmf(self, parameters):
        self.scenario_number = parameters["scenario_number"]
        self.line_selector_expression = parameters["line_selector_expression"]

        self.scenario = _m.Modeller().emmebank.scenario(self.scenario_number)

        try:
            self._execute()
        except Exception as e:
            self.tool_run_msg = _m.PageBuilder.format_exception(e, _traceback.format_exc())
            raise

    # ---
    # ---MAIN EXECUTION CODE

    def _execute(self):
        with _m.logbook_trace(
            name="{classname} v{version}".format(classname=(self.__class__.__name__), version=self.version),
            attributes=self._GetAtts(),
        ):

            with _util.temp_extra_attribute_manager(self.scenario, "TRANSIT_LINE") as lineFlagAttribute:
                self._FlagLines(lineFlagAttribute.id)

                network = self.scenario.get_network()
                print("Loaded network")

                linesToReverse = [line for line in network.transit_lines() if line[lineFlagAttribute.id]]
                if len(linesToReverse) == 0:
                    _m.logbook_write("Found no lines to reverse")
                    return
                print("Found %s lines to reverse" % len(linesToReverse))

                self._ReverseLines(linesToReverse)

                self.scenario.publish_network(network)

    ##########################################################################################################

    # ----Sub functions

    def _GetAtts(self):
        atts = {
            "Scenario": str(self.scenario.id),
            "Line Selector Expression": self.line_selector_expression,
            "Version": self.version,
            "self": self.__MODELLER_NAMESPACE__,
        }

        return atts

    def _FlagLines(self, flagAttributeId):
        spec = {
            "result": flagAttributeId,
            "expression": "1",
            "aggregation": None,
            "selections": {"transit_line": self.line_selector_expression},
            "type": "NETWORK_CALCULATION",
        }

        tool = _MODELLER.tool("inro.emme.network_calculation.network_calculator")
        tool(spec, scenario=self.scenario)

    def _ReverseLines(self, linesToReverse):
        network = linesToReverse[0].network
        attNames = network.attributes("TRANSIT_SEGMENT")

        errorLines = []
        reversedLines = []

        self.TRACKER.start_process(len(linesToReverse))
        for line in linesToReverse:
            try:
                newId = self._ReverseLine(line, network, attNames)
                reversedLines.append((line.id, newId))
            except Exception as e:
                t = line.id, e.__class__.__name__, str(e)
                errorLines.append(t)
            self.TRACKER.complete_subtask()
        self.TRACKER.complete_task()

        self._WriteMainReport(reversedLines)
        if errorLines:
            self._WriteErrorReport(errorLines)

    def _ReverseLine(self, line, network, attNames):
        # Get the ID of the new, reversed line
        newId = self._GetNewId(line.id, network)

        # Get the segment attributes
        segmentAttributes = []
        for segment in line.segments(False):
            d = {}
            for attName in attNames:
                d[attName] = segment[attName]
            segmentAttributes.append(d)

        # Get and reverse the line itinerarry
        newItinerary = [node.number for node in line.itinerary()]
        newItinerary.reverse()

        # Create the copy
        copy = network.create_transit_line(newId, line.vehicle.id, newItinerary)
        for segment in copy.segments(False):
            d = segmentAttributes.pop()  # Pops from the tail of the list, reversing the order
            for attName, value in d.items():
                segment[attName] = value

        return newId

    def _GetNewId(self, originalId, network):
        if len(originalId) < 6:
            for i in range(ord("a"), ord("z") + 1):
                newId = originalId + chr(i)
                if network.transit_line(newId) is None:
                    return newId
            raise Exception("Could not create a valid ID for the reversed line")

        lastDigit = originalId[5]
        for i in range(ord(lastDigit), ord("z") + 1):
            newId = originalId[:-1] + chr(i)
            if network.transit_line(newId) is None:
                return newId
        raise Exception("Could not create a valid ID for the reverse line")

    def _WriteMainReport(self, reversedLines):
        acc = ""
        for originalId, newId in reversedLines:
            acc += "<tr><td>" + self.escape(originalId) + "</td><td>" + self.escape(newId) + "</td></tr>"

        body = (
            """
        <table>
            <tr>
                <th>Original ID</th>
                <th>Reversed ID</th>
            </tr>
        """
            + acc
            + """
        </table>
        """
        )

        pb = _m.PageBuilder(title="Reversed Lines Report")
        pb.wrap_html(body=str(body))
        _m.logbook_write("Reversed lines report", value=pb.render())

    def _WriteErrorReport(self, errorLines):
        acc = ""

        for lineId, errorType, errorMsg in errorLines:
            acc += (
                "<tr><td>"
                + self.escape(lineId)
                + "</td><td>"
                + self.escape(errorType)
                + "</td><td>"
                + self.escape(errorMsg)
                + "</td></tr>"
            )

        body = (
            """
        <table>
            <tr>
                <th>Line ID</th>
                <th>Error Type</th
                <th>Error Message</th>
            </tr>
            """
            + bcc
            + """
        </table>
        """
        )

        pb = _m.PageBuilder(title="Error Report")
        pb.wrap_html(body=str(body))
        _m.logbook_write("Error report", value=pb.render())

    def escape(self, htmlstring):
        escapes = {'"': "&quot;", "'": "&#39;", "<": "&lt;", ">": "&gt;"}
        # This is done first to prevent escaping other escapes.
        htmlstring = htmlstring.replace("&", "&amp;")
        for seq, esc in escapes.items():
            htmlstring = htmlstring.replace(seq, esc)
        return htmlstring

    @_m.method(return_type=_m.TupleType)
    def percent_completed(self):
        return self.TRACKER.get_progress()

    @_m.method(return_type=str)
    def tool_run_msg_status(self):
        return self.tool_run_msg
