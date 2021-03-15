# -*- coding: utf-8 -*-
import concurrent
from concurrent.futures.thread import ThreadPoolExecutor
from pathlib import Path
import os
from datetime import datetime

from API.mdf import MDF
from API.gui import plot
from API.blocks.utils import MdfException, ApiException

class Main():
    def __init__(self, cmd_args=None):
        self.function = cmd_args.function   #chninfo, export
        self.source = cmd_args.source
        self.recursive = cmd_args.subdir
        self.out_dir = cmd_args.out_dir
        self.include_attr = cmd_args.include_attr
        self.chn_dir = cmd_args.chn_dir
        self.format = cmd_args.format
        self.stats = cmd_args.stats
        self.raster = cmd_args.raster
        self.groupby = cmd_args.groupby
        self.with_index = cmd_args.with_index
        self.start_time = cmd_args.start_time
        self.end_time = cmd_args.end_time
        self.from_zero = cmd_args.from_zero
        self.empty_chn = cmd_args.empty_chn
        self.use_display_names = cmd_args.use_sname

        self.message = []

        if self.out_dir is not None:
            if not os.path.exists(self.out_dir):
                exc_type = "ApiException_001"
                exc_args = f"Invalid output directory path\t{self.out_dir}"
                self.message.append(self.msg_format(exc_type, exc_args))
                # err_msg = "Invalid export format"
                # raise ApiException(err_msg)
                self.write_log(self.msg_format(self.message))
                print(exc_args)
                return

        extensions = (".dat", "mdf", ".mf4")
        path_dict = {}

        for path in self.source:
            if os.path.isfile(path):
                if os.path.splitext(path)[1] in extensions:
                    path_dict[path] = None

                elif os.path.splitext(path)[1] == ".fls":
                    with open(path, "r") as lines:
                        for line in lines:
                            line = line.split('\n')[0]
                            try:
                                file_path, chn_path = (x for x in line.split('\t'))
                            except:
                                file_path = line
                                chn_path = None

                            if len(file_path) == 0:
                                continue
                            elif not os.path.isfile(file_path):
                                exc_type = "ApiException_101"
                                exc_args = f'File does not exist\t{file_path}'
                                self.message.append(self.msg_format(exc_type, exc_args))
                                # raise MdfException(f'{file_path}\nFile does not exist')
                                # err_msg = "Invalid mdf file path"
                                # self.message.append(self.msg_format(err_msg, f"{file_path}"))
                                print(exc_args)
                            else:
                                path_dict[file_path] = chn_path
            else:
                if os.path.exists(path):
                    if self.recursive:
                        for type in extensions:
                            for file_path in Path(path).rglob('*'+type):
                                path_dict[file_path] = None
                    else:
                        for type in extensions:
                            for file_path in Path(path).glob('*'+type):
                                path_dict[file_path] = None

        run_thread = False
        if len(path_dict) == 0 :
            exc_type = "ApiException_103"
            exc_args = f'Empty source files\t{self.source}'
            self.message.append(self.msg_format(exc_type, exc_args))
            # raise ApiException('No source files')
            # err_msg = "No source files"
            self.write_log("\n".join(self.message))
            print(exc_args)
            return
        elif len(path_dict) > 1 :
            run_thread = True

        # API Execution
        if self.function not in ("chninfo", "export", "plot"):
            exc_type = "ApiException_002"
            exc_args = f"Function argument should be either 'chninfo' or 'export'\t{self.function}"
            self.message.append(self.msg_format(exc_type, exc_args))
            # err_msg = "Function argument should be either 'chninfo' or 'export'"
            # raise ApiException(err_msg)
            self.write_log("\n".join(self.message))
            print(exc_args)
            return

        elif self.function == "chninfo":
            for file_path in path_dict:
                self.export_chn(file_path, self.out_dir, self.include_attr)

        elif self.function == "export":   # export
            start = datetime.now()
            if self.format.lower() not in ("csv", "mdf", "mat"):
                exc_type = "ApiException_003"
                exc_args = "Invalid export format\t"
                self.message.append(self.msg_format(exc_type, exc_args))
                # err_msg = "Invalid export format"
                # raise ApiException(err_msg)
                self.write_log(self.msg_format(self.message))
                print(exc_args)
                return
            else:
                thread_list = []
                name_dict = None

                if self.groupby == "g":
                    self.single_time_base = False
                    self.with_index = True
                else:
                    self.single_time_base = True

                with ThreadPoolExecutor() as executor:
                    for file_path in path_dict:
                        # get channel list from chn file
                        required_channels = ()
                        if self.chn_dir is not None:
                            name_dict = self.read_chn(self.chn_dir)
                            required_channels = tuple(name_dict.keys())
                        else:
                            if path_dict[file_path] is not None:
                                name_dict = self.read_chn(path_dict[file_path])
                                required_channels = tuple(name_dict.keys())

                        kwargs = {"name_dict": name_dict}

                        try:
                            mdf = MDF(file_path, channels=required_channels, **kwargs)
                            if len(mdf.channels_db) < 2:
                                exc_type = "MdfException_212"
                                exc_args = f'Empty channels\t{file_path}'
                                self.message.append(self.msg_format(exc_type, exc_args))
                                # err_msg = "Empty channels"
                                # raise MdfException(f'{file_path}\nEmpty channels')
                                # self.message.append(self.msg_format(err_msg, f"{file_path}\t{path_dict[file_path]}"))
                                # print(err_msg)
                                continue
                        except Exception as e:
                            if type(e) == MdfException:
                                exc_type = e.__class__.__name__ + "211"
                                self.message.append(self.msg_format(exc_type, e.args[0]))
                            else:
                                exc_type = "MdfException_219"
                                exc_args = f'Unknown error\t{file_path}'
                                self.message.append(self.msg_format(exc_type, exc_args))
                            continue

                        kwargs = {"single_time_base": self.single_time_base,
                                  "time_from_zero": self.from_zero,
                                  "use_display_names": self.use_display_names,
                                  "empty_channels": self.empty_chn,
                                  "raster": self.raster,
                                  "stats": self.stats,
                                  "groupby": self.groupby,
                                  "with_index": self.with_index
                                  }

                        if run_thread:
                            thread_list.append(executor.submit(mdf.export, self.format, self.out_dir, **kwargs))
                        else:
                            try:
                                mdf.export(self.format, self.out_dir, **kwargs)
                            except:
                                exc_type = "MdfException_221"
                                exc_args = f'Export failed\t{file_path}'
                                self.message.append(self.msg_format(exc_type, exc_args))
                for execution in concurrent.futures.as_completed(thread_list):
                    try:
                        execution.result()
                    except Exception as e:
                        self.message.append(self.msg_format(e.__class__.__name__, e.args[0]))

                print(datetime.now()-start)

        else:   # "plot"
            for file_path in path_dict:
                if self.chn_dir is not None:
                    channels = self.read_chn(self.chn_dir)[0]
                    signals = MDF(file_path).select(channels)
                    plot.plot(signals)
                else:
                    if path_dict[file_path] is not None:
                        channels = self.read_chn(path_dict[file_path])
                        signals = MDF(file_path).select(channels)
                        plot.plot(signals)

        if len(self.message) == 0:
            self.write_log(datetime.now().strftime("%Y-%m-%d, %H:%M:%S") + "\tOK")
        else:
            self.write_log("\n".join(self.message))

    def read_chn(self, chn_dir):
        # read .chn file and return channel list
        ch_dict = {}
        if not os.path.isfile(chn_dir):
            exc_type = "ApiException_102"
            exc_args = f'File does not exist\t{chn_dir}'
            self.message.append(self.msg_format(exc_type, exc_args))
        else:
            with open(chn_dir, "r") as lines:
                for line in lines:
                    line = line.split("\n")[0]
                    try:
                        key, value = (x for x in line.split('\t'))
                    except:
                        key = line
                        value = ""

                    if len(key) == 0 or key[0] == "$":
                        continue
                    else:
                        ch_dict[key] = value

        return ch_dict

    def export_chn(self, file_path, out_dir=None, include_attr=False):
        channels = []

        if out_dir is None:
            out_dir = os.path.splitext(file_path)[0] + ".chn"
        else:
            if os.path.exists(out_dir):
                out_dir = os.path.split(out_dir)[0]
                file_name = os.path.basename(file_path).split(".")[0] + ".chn"
                out_dir = os.path.join(out_dir, file_name)

        try:
            mdf = MDF(file_path)
        except Exception as e:
            if type(e) == MdfException:
                exc_type = e.__class__.__name__+"201"
                self.message.append(self.msg_format(exc_type, e.args[0]))
            else:
                exc_type = "MdfException_209"
                exc_args = f'Unknown error\t{file_path}'
                self.message.append(self.msg_format(exc_type, exc_args))

        if not include_attr:
            try:
                # channels.append([mdf.start_time.strftime('%Y-%m-%d')])
                with open(out_dir, "w") as f:
                    f.write(mdf.start_time.strftime('%Y-%m-%d %H:%M:%S')+"\n")
                    for channel in mdf.channels_db:
                        f.write(channel + "\n")
            except Exception as e:
                print(e)

        else:
            channels.append([mdf.start_time.strftime('%Y-%m-%d %Y-%m-%d %H:%M:%S')])
            for item in mdf.channels_db.items():
                for index in item[1]:
                    gp_nr, ch_nr = index[0], index[1]
                    grp = mdf.groups[gp_nr]
                    channel = grp.channels[ch_nr]

                    channels.append([channel.name,
                                     str(channel.sampling_rate),
                                     mdf.get_channel_unit(channel.name,gp_nr,ch_nr),
                                     f'Channel group {gp_nr}',
                                     str(channel.comment)
                                     ])
            try:
                with open(out_dir, "w") as f:
                    for channel in channels:
                        f.write("\t".join(channel) + "\n")
            except Exception as e:
                print(e)

    def msg_format(self, message, details=""):

        separator = "-" * 80
        now = datetime.now().strftime("%Y-%m-%d, %H:%M:%S")

        sections = [now, message, details]
        msg = "\t".join(sections)
        msg += "\n" + separator
        return msg

    def write_log(self, message="", out_dir=None):

        if out_dir is None:
            out_dir = os.environ['APPDATA'] + "\\mdfstudioapi.log"
        else:
            if os.path.exists(out_dir):
                out_dir = os.path.split(out_dir)[0]
                file_name = "\\mdfstudioapi.log"
                out_dir = os.path.join(out_dir, file_name)
            else:
                print("Invalid output directory path")

        try:
            with open(out_dir, "w") as f:
                f.write(message)

        except Exception as e:
            print(e)