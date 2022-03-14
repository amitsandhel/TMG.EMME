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

import inro.modeller as _m
import traceback as _traceback
from contextlib import contextmanager
from os import path as _path
from datetime import datetime as _datetime
import shutil as _shutil
import zipfile as _zipfile
import tempfile as _tempfile

_m.InstanceType = object
_m.TupleType = object
_m.ListType = list

_MODELLER = _m.Modeller()  # Instantiate Modeller once.
_util = _MODELLER.module("tmg2.utilities.general_utilities")
_inro_export_util = _MODELLER.module("inro.emme.utility.export_utilities")
_export_modes = _MODELLER.tool("inro.emme.data.network.mode.export_modes")
_export_vehicles = _MODELLER.tool("inro.emme.data.network.transit.export_vehicles")
_export_base_network = _MODELLER.tool("inro.emme.data.network.base.export_base_network")
_export_transit_lines = _MODELLER.tool("inro.emme.data.network.transit.export_transit_lines")
_export_link_shapes = _MODELLER.tool("inro.emme.data.network.base.export_link_shape")
_export_turns = _MODELLER.tool("inro.emme.data.network.turn.export_turns")
_export_attributes = _MODELLER.tool("inro.emme.data.extra_attribute.export_extra_attributes")
_export_functions = _MODELLER.tool("inro.emme.data.function.export_functions")
_pdu = _MODELLER.module("tmg2.utilities.pandas_utils")
_tmgTPB = _MODELLER.module("tmg2.utilities.TMG_tool_page_builder")


class ExportNetworkPackage(_m.Tool()):
    version = "1.2.2"
    tool_run_msg = ""
    number_of_tasks = 11  # For progress reporting, enter the integer number of tasks here

    Scenario = _m.Attribute(_m.InstanceType)
    ExportFile = _m.Attribute(str)
    ExportAllFlag = _m.Attribute(bool)
    AttributeIdsToExport = _m.Attribute(_m.ListType)
    ExportMetadata = _m.Attribute(str)
    ExportToEmmeOldVersion = _m.Attribute(bool)

    export_attributes = _m.Attribute(str)
    scenario_number = _m.Attribute(int)
    # xtmf_ScenarioString = _m.Attribute(str)

    def __init__(self):
        self.TRACKER = _util.progress_tracker(self.number_of_tasks)  # init the progress_tracker

        self.Scenario = _MODELLER.scenario  # Default is primary scenario
        self.ExportMetadata = ""
        self.ExportToEmmeOldVersion = False

    def page(self):
        pb = _tmgTPB.TmgToolPageBuilder(
            self,
            title="Export Network Package v%s" % self.version,
            description="Exports all scenario data files (modes, vehicles, nodes, links, transit lines, link shape, "
            "turns) to a compressed network package file (*.nwp). Descriptions that are empty, have single "
            "quotes, or double quotes will be replaced by 'No Description', grave accents (`), and spaces.",
            branding_text="- TMG Toolbox",
        )

        if self.tool_run_msg:
            pb.tool_run_status(self.tool_run_msg_status)

        pb.add_select_scenario("Scenario", title="Scenario", allow_none=False)

        pb.add_select_file(
            "ExportFile",
            title="File name",
            window_type="save_file",
            file_filter="*.nwp",
        )

        pb.add_checkbox(
            "ExportToEmmeOldVersion",
            label="Export it to be compatible with Emme 4.3?",
            note="Descriptions longer than 20 characters will be trimmed.",
        )

        pb.add_checkbox("ExportAllFlag", label="Export all extra attributes?")

        pb.add_select(
            "AttributeIdsToExport",
            keyvalues=self._get_select_attribute_options_json(),
            title="Extra Attributes",
            searchable=True,
            note="Optional",
        )

        pb.add_text_box("ExportMetadata", size=255, multi_line=True, title="Export comments")

        pb.add_html(
            """
<script type="text/javascript">
    $(document).ready(function() {
        var tool = new inro.modeller.util.Proxy(%s);
        if (tool.check_all_flag()) {
            $("#AttributeIdsToExport").prop('disabled', true);
        } else {
            $("#AttributeIdsToExport").prop('disabled', false);
        }
        $("#Scenario").on('change', function() {
            $(this).commit();
            $("#AttributeIdsToExport").empty().append(tool._get_select_attribute_options_html())
            inro.modeller.page.preload("#AttributeIdsToExport");
            $("#AttributeIdsToExport").trigger('change');
        });
        $("#ExportAllFlag").on('change', function() {
            $(this).commit();
            var not_flag = ! tool.check_all_flag();
            var flag = tool.check_all_flag();
            $("#AttributeIdsToExport").prop('disabled', flag);
        });
    });
</script>"""
            % pb.tool_proxy_tag
        )

        return pb.render()

    def run(self):
        self.tool_run_msg = ""
        self.TRACKER.reset()

        if self.ExportFile is None:
            raise IOError("Export file not specified")

        self.ExportFile = _path.splitext(self.ExportFile)[0] + ".nwp"

        try:
            self._execute()
        except Exception as e:
            self.tool_run_msg = _m.PageBuilder.format_exception(e, _traceback.format_exc())
            raise

        self.tool_run_msg = _m.PageBuilder.format_info("Done. Scenario exported to %s" % self.ExportFile)

    @_m.method(return_type=bool)
    def check_all_flag(self):
        return self.ExportAllFlag

    def __call__(self, scenario_number, ExportFile, export_attributes):

        self.Scenario = _MODELLER.emmebank.scenario(scenario_number)
        if self.Scenario is None:
            raise Exception("Scenario %s was not found!" % scenario_number)

        self.ExportFile = ExportFile
        if export_attributes.lower() == "all":
            self.ExportAllFlag = True  # if true, self.AttributeIdsToExport gets set in execute
        else:
            cells = export_attributes.split(",")
            self.AttributeIdsToExport = [str(c.strip()) for c in cells if c.strip()]  # Clean out null values

        try:
            self._execute()
        except Exception as e:
            msg = str(e) + "\n" + _traceback.format_exc()
            raise Exception(msg)

    def run_xtmf(self, parameters):
        # xtmf_ScenarioNumber, ExportFile, xtmf_AttributeIdString
        self.ExportFile = parameters["export_file"]
        self.Scenario = _m.Modeller().emmebank.scenario(parameters["scenario_number"])
        if self.Scenario is None:
            raise Exception("Scenario %s was not found!" % self.scenario_number)
        xtmf_AttributeIdString = parameters["extra_attributes"]

        if xtmf_AttributeIdString.lower() == "all":
            self.ExportAllFlag = True  # if true, self.AttributeIdsToExport gets set in execute
        else:
            cells = xtmf_AttributeIdString.split(",")
            self.AttributeIdsToExport = [str(c.strip()) for c in cells if c.strip()]  # Clean out null values
        try:
            self._execute()
        except Exception as e:
            msg = str(e) + "\n" + _traceback.format_exc()
            raise Exception(msg)

    def _execute(self):
        logbook_attributes = {
            "Scenario": str(self.Scenario.id),
            "Export File": _path.splitext(self.ExportFile)[0],
            "Version": self.version,
            "self": self.__MODELLER_NAMESPACE__,
        }
        with _m.logbook_trace(
            name="%s v%s" % (self.__class__.__name__, self.version),
            attributes=logbook_attributes,
        ):
            # Due to the dynamic nature of the selection process, it could happen that attributes are
            # selected which don't exist in the current scenario. The method checks early to catch
            # any problems
            defined_attributes = [att.name for att in self.Scenario.extra_attributes()]
            if self.ExportAllFlag:
                self.AttributeIdsToExport = defined_attributes
            else:
                missing_attributes = set(self.AttributeIdsToExport).difference(defined_attributes)
                if missing_attributes:
                    raise IOError(
                        "Attributes [%s] not defined in scenario %s"
                        % (", ".join(missing_attributes), self.Scenario.number)
                    )

            with _zipfile.ZipFile(self.ExportFile, "w", _zipfile.ZIP_DEFLATED) as zf, self._temp_file() as temp_folder:
                version_file = _path.join(temp_folder, "version.txt")
                with open(version_file, "w") as writer:
                    writer.write("%s\n%s" % (str(5.0), _util.get_emme_version(returnType=str)))
                zf.write(version_file, arcname="version.txt")

                info_path = _path.join(temp_folder, "info.txt")
                self._write_info_file(info_path)
                zf.write(info_path, arcname="info.txt")

                self._batchout_modes(temp_folder, zf)
                self._batchout_vehicles(temp_folder, zf)
                self._batchout_base(temp_folder, zf)
                self._batchout_shapes(temp_folder, zf)
                self._batchout_lines(temp_folder, zf)
                self._batchout_turns(temp_folder, zf)
                self._batchout_functions(temp_folder, zf)

                if len(self.AttributeIdsToExport) > 0:
                    self._batchout_extra_attributes(temp_folder, zf)
                else:
                    self.TRACKER.complete_task()

                if self.Scenario.has_traffic_results:
                    self._batchout_traffic_results(temp_folder, zf)
                self.TRACKER.complete_task()

                if self.Scenario.has_transit_results:
                    self._batchout_transit_results(temp_folder, zf)
                self.TRACKER.complete_task()

    @_m.logbook_trace("Exporting modes")
    def _batchout_modes(self, temp_folder, zf):
        export_file = _path.join(temp_folder, "modes.201")
        self.TRACKER.run_tool(_export_modes, export_file=export_file, scenario=self.Scenario)
        zf.write(export_file, arcname="modes.201")

    @_m.logbook_trace("Exporting vehicles")
    def _batchout_vehicles(self, temp_folder, zf):
        export_file = _path.join(temp_folder, "vehicles.202")
        if self.Scenario.element_totals["transit_vehicles"] == 0:
            self._export_blank_batch_file(export_file, "vehicles")
            self.TRACKER.complete_task()
        else:
            self.TRACKER.run_tool(_export_vehicles, export_file=export_file, scenario=self.Scenario)
        zf.write(export_file, arcname="vehicles.202")

    @_m.logbook_trace("Exporting base network")
    def _batchout_base(self, temp_folder, zf):
        export_file = _path.join(temp_folder, "base.211")
        self.TRACKER.run_tool(
            _export_base_network,
            export_file=export_file,
            scenario=self.Scenario,
            export_format="ENG_DATA_FORMAT",
        )
        zf.write(export_file, arcname="base.211")

    @_m.logbook_trace("Exporting link shapes")
    def _batchout_shapes(self, temp_folder, zf):
        export_file = _path.join(temp_folder, "shapes.251")
        self.TRACKER.run_tool(_export_link_shapes, export_file=export_file, scenario=self.Scenario)
        zf.write(export_file, arcname="shapes.251")

    @_m.logbook_trace("Exporting transit lines")
    def _batchout_lines(self, temp_folder, zf):
        export_file = _path.join(temp_folder, "transit.221")
        if self.Scenario.element_totals["transit_lines"] == 0:
            self._export_blank_batch_file(export_file, "lines")
            self.TRACKER.complete_task()
        else:
            # check if the description is empty or has single quote
            network = self.Scenario.get_network()
            for line in network.transit_lines():
                if len(line.description) == 0:
                    line.description = "No Description"
                else:
                    line.description = line.description.replace("'", "`").replace('"', " ")
                    if len(line.description) > 20 and self.ExportToEmmeOldVersion:
                        line.description = line.description[0:19]
            self.Scenario.publish_network(network)

            self.TRACKER.run_tool(
                _export_transit_lines,
                export_file=export_file,
                scenario=self.Scenario,
                export_format="ENG_DATA_FORMAT",
            )
        zf.write(export_file, arcname="transit.221")

    @_m.logbook_trace("Exporting turns")
    def _batchout_turns(self, temp_folder, zf):
        export_file = _path.join(temp_folder, "turns.231")
        if self.Scenario.element_totals["turns"] == 0:
            self.TRACKER.complete_task()
        else:
            self.TRACKER.run_tool(
                _export_turns,
                export_file=export_file,
                scenario=self.Scenario,
                export_format="ENG_DATA_FORMAT",
            )
            zf.write(export_file, arcname="turns.231")

    @_m.logbook_trace("Exporting Functions")
    def _batchout_functions(self, temp_folder, zf):
        export_file = _path.join(temp_folder, "functions.411")
        self.TRACKER.run_tool(_export_functions, export_file=export_file)
        zf.write(export_file, arcname="functions.411")

    @_m.logbook_trace("Exporting extra attributes")
    def _batchout_extra_attributes(self, temp_folder, zf):
        _m.logbook_write("List of attributes: %s" % self.AttributeIdsToExport)

        extra_attributes = [self.Scenario.extra_attribute(id_) for id_ in self.AttributeIdsToExport]
        types = set([att.type.lower() for att in extra_attributes])

        self.TRACKER.run_tool(
            _export_attributes,
            extra_attributes,
            temp_folder,
            field_separator=",",
            scenario=self.Scenario,
            export_format="SCI_DATA_FORMAT",
        )
        for t in types:
            if t == "transit_segment":
                t = "segment"
            filename = _path.join(temp_folder, "extra_%ss_%s.csv" % (t, self.Scenario.number))
            zf.write(filename, arcname="exatt_%ss.241" % t)
        summary_file = _path.join(temp_folder, "exatts.241")
        self._export_attribute_definition_file(summary_file, extra_attributes)
        zf.write(summary_file, arcname="exatts.241")

    def _batchout_traffic_results(self, temp_folder, zf):
        link_filepath = _path.join(temp_folder, "link_results.csv")
        turn_filepath = _path.join(temp_folder, "turn_results.csv")
        traffic_result_attributes = ["auto_volume", "additional_volume", "auto_time"]

        links = _pdu.load_link_dataframe(self.Scenario)[traffic_result_attributes]
        links.to_csv(link_filepath, index=True)
        zf.write(link_filepath, arcname=_path.basename(link_filepath))

        turns = _pdu.load_turn_dataframe(self.Scenario)
        if not (turns is None):
            turns = turns[traffic_result_attributes]
            turns.to_csv(turn_filepath)
            zf.write(turn_filepath, arcname=_path.basename(turn_filepath))

    def _batchout_transit_results(self, temp_folder, zf):
        segment_filepath = _path.join(temp_folder, "segment_results.csv")
        result_attributes = ["transit_boardings", "transit_time", "transit_volume"]
        segments = _pdu.load_transit_segment_dataframe(self.Scenario)[result_attributes]
        segments.to_csv(segment_filepath)
        zf.write(segment_filepath, arcname=_path.basename(segment_filepath))

        aux_transit_filepath = _path.join(temp_folder, "aux_transit_results.csv")
        aux_result_attributes = ["aux_transit_volume"]
        aux_transit = _pdu.load_link_dataframe(self.Scenario)[aux_result_attributes]
        aux_transit.to_csv(aux_transit_filepath)
        zf.write(aux_transit_filepath, arcname=_path.basename(aux_transit_filepath))

    @contextmanager
    def _temp_file(self):
        foldername = _tempfile.mkdtemp()
        _m.logbook_write("Created temporary directory at `%s`" % foldername)
        try:
            yield foldername
        finally:
            _shutil.rmtree(foldername, True)
            _m.logbook_write("Deleted temporary directory at `%s`" % foldername)

    @staticmethod
    def _export_blank_batch_file(filename, t_record):
        with open(filename, "w") as file_:
            file_.write("t %s init" % t_record)

    @staticmethod
    def _export_attribute_definition_file(filename, attribute_list):
        with open(filename, "w") as writer:
            writer.write("name,type, default")
            for att in attribute_list:
                writer.write(
                    "\n{name},{type},{default},'{desc}'".format(
                        name=att.name,
                        type=att.type,
                        default=att.default_value,
                        desc=att.description,
                    )
                )

    def _write_info_file(self, fp):
        with open(fp, "w") as writer:
            bank = _MODELLER.emmebank
            lines = [
                str(bank.title),
                str(bank.path),
                "%s - %s" % (self.Scenario, self.Scenario.title),
                _datetime.now().strftime("%Y-%m-%d %H:%M"),
                self.ExportMetadata,
            ]
            writer.write("\n".join(lines))

    def _get_select_attribute_options_json(self):
        keyval = {}
        for att in self.Scenario.extra_attributes():
            label = "{id} ({domain}) - {name}".format(id=att.name, domain=att.type, name=att.description)
            keyval[att.name] = label
        return keyval

    @_m.method(return_type=str)
    def _get_select_attribute_options_html(self):
        list_ = []
        for att in self.Scenario.extra_attributes():
            label = "{id} ({domain}) - {name}".format(id=att.name, domain=att.type, name=att.description)
            html = str('<option value="{id}">{text}</option>'.format(id=att.name, text=label))
            list_.append(html)
        return "\n".join(list_)

    @_m.method(return_type=_m.TupleType)
    def percent_completed(self):
        return self.TRACKER.get_progress()

    @_m.method(return_type=str)
    def tool_run_msg_status(self):
        return self.tool_run_msg
