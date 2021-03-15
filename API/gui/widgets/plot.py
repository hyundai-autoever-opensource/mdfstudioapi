# -*- coding: utf-8 -*-
"""
    Edit history
    Author : yda
    Date : 2021-03-15

    Functions
    ---------
    *   init   - Not to initiate info window
"""
from datetime import timedelta
from functools import partial, reduce
import logging
import os
from pathlib import Path
from time import perf_counter

import numpy as np
from PyQt5 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

from ...mdf import MDF
from ...signals import Signal
from .formated_axis import FormatedAxis
from .channel_display import ChannelDisplay
from .cursor import Cursor
from .list import ListWidget
from .list_item import ListItem
from ..utils import COLORS

bin_ = bin

HERE = Path(__file__).resolve().parent


if not hasattr(pg.InfiniteLine, "addMarker"):
    logger = logging.getLogger("asammdf")
    message = (
        "Old pyqtgraph package: Please install the latest pyqtgraph from the "
        "github develop branch\n"
        "pip install -I --no-deps "
        "https://github.com/pyqtgraph/pyqtgraph/archive/develop.zip"
    )
    logger.warning(message)


class PlotSignal(Signal):
    def __init__(self, signal, index=0, fast=False, trim_info=None):
        super().__init__(
            signal.samples,
            signal.timestamps,
            signal.unit,
            signal.name,
            signal.conversion,
            signal.comment,
            signal.raw,
            signal.master_metadata,
            signal.display_name,
            signal.attachment,
            signal.source,
            signal.bit_count,
            signal.stream_sync,
            invalidation_bits=signal.invalidation_bits,
            encoding=signal.encoding,
        )

        self.uuid = getattr(signal, "uuid", os.urandom(6).hex())
        self.mdf_uuid = getattr(signal, "mdf_uuid", os.urandom(6).hex())

        self.group_index = getattr(signal, "group_index", -1)
        self.channel_index = getattr(signal, "channel_index", -1)
        self.precision = getattr(signal, "precision", 6)

        self._mode = "raw"

        self.enable = True
        self.format = "phys"

        self.individual_axis = False
        self.computed = signal.computed
        self.computation = signal.computation

        self.trim_info = None

        # take out NaN values
        samples = self.samples
        if samples.dtype.kind not in "SUV":
            nans = np.isnan(samples)
            if np.any(nans):
                self.samples = self.samples[~nans]
                self.timestamps = self.timestamps[~nans]

        if self.conversion:
            samples = self.conversion.convert(self.samples)
            if samples.dtype.kind not in "SUV":
                nans = np.isnan(samples)
                if np.any(nans):
                    self.raw_samples = self.samples[~nans]
                    self.phys_samples = samples[~nans]
                    self.timestamps = self.timestamps[~nans]
                    self.samples = self.samples[~nans]
                else:
                    self.raw_samples = self.samples
                    self.phys_samples = samples
            else:
                self.phys_samples = self.raw_samples = self.samples
        else:
            self.phys_samples = self.raw_samples = self.samples

        self.plot_samples = self.phys_samples
        self.plot_timestamps = self.timestamps

        self._stats = {
            "range": (0, -1),
            "range_stats": {},
            "visible": (0, -1),
            "visible_stats": {},
            "fmt": "",
        }

        if hasattr(signal, "color"):
            color = signal.color or COLORS[index % 10]
        else:
            color = COLORS[index % 10]
        self.color = color

        if len(self.phys_samples) and not fast:

            if self.phys_samples.dtype.kind in "SUV":
                self.is_string = True
                self._min = ""
                self._max = ""
                self._avg = ""
                self._rms = ""
            else:
                self.is_string = False
                samples = self.phys_samples[np.isfinite(self.phys_samples)]
                if len(samples):
                    self._min = np.nanmin(samples)
                    self._max = np.nanmax(samples)
                    self._avg = np.mean(samples)
                    self._rms = np.sqrt(np.mean(np.square(samples)))
                else:
                    self._min = "n.a."
                    self._max = "n.a."
                    self._avg = "n.a."
                    self._rms = "n.a."

            if self.raw_samples.dtype.kind in "SUV":
                self._min_raw = ""
                self._max_raw = ""
                self._avg_raw = ""
                self._rms_raw = ""
            else:

                samples = self.raw_samples[np.isfinite(self.raw_samples)]
                if len(samples):
                    self._min_raw = np.nanmin(samples)
                    self._max_raw = np.nanmax(samples)
                    self._avg_raw = np.mean(samples)
                    self._rms_raw = np.sqrt(np.mean(np.square(samples)))
                else:
                    self._min_raw = "n.a."
                    self._max_raw = "n.a."
                    self._avg_raw = "n.a."
                    self._rms_raw = "n.a."

            self.empty = False

        else:
            self.empty = True
            if self.phys_samples.dtype.kind in "SUV":
                self.is_string = True
                self._min = ""
                self._max = ""
                self._rms = ""
                self._avg = ""
                self._min_raw = ""
                self._max_raw = ""
                self._avg_raw = ""
                self._rms_raw = ""
            else:
                self.is_string = False
                self._min = "n.a."
                self._max = "n.a."
                self._rms = "n.a."
                self._avg = "n.a."
                self._min_raw = "n.a."
                self._max_raw = "n.a."
                self._avg_raw = "n.a."
                self._rms_raw = "n.a."

        self.mode = "phys"
        if not fast:
            self.trim(*(trim_info or (None, None, 1900)))

    @property
    def min(self):
        return self._min if self.mode == "phys" else self._min_raw

    @min.setter
    def min(self, min):
        self._min = min

    @property
    def max(self):
        return self._max if self.mode == "phys" else self._max_raw

    @max.setter
    def max(self, max):
        self._max = max

    @property
    def avg(self):
        return self._avg if self.mode == "phys" else self._avg_raw

    @avg.setter
    def avg(self, avg):
        self._avg = avg

    @property
    def rms(self):
        return self._rms if self.mode == "phys" else self._rms_raw

    @rms.setter
    def rms(self, rms):
        self._rms = rms

    def cut(self, start=None, stop=None, include_ends=True, interpolation_mode=0):
        cut_sig = super().cut(start, stop, include_ends, interpolation_mode)

        cut_sig.group_index = self.group_index
        cut_sig.channel_index = self.channel_index
        cut_sig.computed = self.computed
        cut_sig.color = self.color
        cut_sig.computation = self.computation
        cut_sig.precision = self.precision
        cut_sig.mdf_uuif = self.mdf_uuid

        return PlotSignal(cut_sig)

    @property
    def mode(self):
        return self._mode

    @mode.setter
    def mode(self, mode):
        if mode != self.mode:
            self._mode = mode
            if mode == "raw":
                self.plot_samples = self.raw_samples
                self.plot_timestamps = self.timestamps
            else:
                self.plot_samples = self.phys_samples
                self.plot_timestamps = self.timestamps

            if self.plot_samples.dtype.kind in "SUV":
                self.is_string = True
            else:
                self.is_string = False

    def get_stats(self, cursor=None, region=None, view_region=None):
        stats = {}
        sig = self
        x = sig.timestamps
        size = len(x)

        if size:

            if sig.is_string:
                stats["overall_min"] = ""
                stats["overall_max"] = ""
                stats["overall_average"] = ""
                stats["overall_rms"] = ""
                stats["overall_start"] = x[0]
                stats["overall_stop"] = x[-1]
                stats["unit"] = ""
                stats["color"] = sig.color
                stats["name"] = sig.name

                if cursor is not None:
                    position = cursor
                    stats["cursor_t"] = position

                    value, kind, format = self.value_at_timestamp(position)

                    if kind in "SUV":
                        fmt = "{}"
                    elif kind == "f":
                        fmt = f"{{:.{self.precision}f}}"
                    else:
                        if format == "hex":
                            fmt = "0x{:X}"
                        elif format == "bin":
                            fmt = "0b{:b}"
                        elif format == "phys":
                            fmt = "{}"

                    value = fmt.format(value)

                    stats["cursor_value"] = value

                else:
                    stats["cursor_t"] = ""
                    stats["cursor_value"] = ""

                stats["selected_start"] = ""
                stats["selected_stop"] = ""
                stats["selected_delta_t"] = ""
                stats["selected_min"] = ""
                stats["selected_max"] = ""
                stats["selected_average"] = ""
                stats["selected_rms"] = ""
                stats["selected_delta"] = ""
                stats["visible_min"] = ""
                stats["visible_max"] = ""
                stats["visible_average"] = ""
                stats["visible_rms"] = ""
                stats["visible_delta"] = ""
            else:
                if isinstance(sig.min, str):
                    kind = "S"
                    fmt = "{}"
                else:
                    kind = sig.min.dtype.kind
                    format = sig.format
                    if kind in "SUV":
                        fmt = "{}"
                    elif kind == "f":
                        fmt = f"{{:.{self.precision}f}}"
                    else:
                        if format == "hex":
                            fmt = "0x{:X}"
                        elif format == "bin":
                            fmt = "0b{:b}"
                        elif format == "phys":
                            fmt = "{}"

                stats["overall_min"] = fmt.format(sig.min)
                stats["overall_max"] = fmt.format(sig.max)
                stats["overall_average"] = sig.avg
                stats["overall_rms"] = sig.rms
                stats["overall_start"] = sig.timestamps[0]
                stats["overall_stop"] = sig.timestamps[-1]
                stats["unit"] = sig.unit
                stats["color"] = sig.color
                stats["name"] = sig.name

                if cursor is not None:
                    position = cursor
                    stats["cursor_t"] = position

                    value, kind, format = self.value_at_timestamp(position)

                    if kind in "SUV":
                        fmt = "{}"
                    elif kind == "f":
                        fmt = f"{{:.{self.precision}f}}"
                    else:
                        if format == "hex":
                            fmt = "0x{:X}"
                        elif format == "bin":
                            fmt = "0b{:b}"
                        elif format == "phys":
                            fmt = "{}"

                    value = fmt.format(value)

                    stats["cursor_value"] = value

                else:
                    stats["cursor_t"] = ""
                    stats["cursor_value"] = ""

                if region:
                    start, stop = region

                    #                     if sig._stats["range"] != (start, stop) or sig._stats["fmt"] != fmt:
                    new_stats = {}
                    new_stats["selected_start"] = start
                    new_stats["selected_stop"] = stop
                    new_stats["selected_delta_t"] = stop - start

                    cut = sig.cut(start, stop)

                    if self.mode == "raw":
                        samples = cut.raw_samples
                    else:
                        samples = cut.phys_samples

                    samples = samples[np.isfinite(samples)]

                    if len(samples):
                        kind = samples.dtype.kind
                        format = self.format

                        if kind in "SUV":
                            fmt = "{}"
                        elif kind == "f":
                            fmt = f"{{:.{self.precision}f}}"
                        else:
                            if format == "hex":
                                fmt = "0x{:X}"
                            elif format == "bin":
                                fmt = "0b{:b}"
                            elif format == "phys":
                                fmt = "{}"

                        new_stats["selected_min"] = fmt.format(np.nanmin(samples))
                        new_stats["selected_max"] = fmt.format(np.nanmax(samples))
                        new_stats["selected_average"] = np.mean(samples)
                        new_stats["selected_rms"] = np.sqrt(np.mean(np.square(samples)))
                        if kind in "ui":
                            new_stats["selected_delta"] = fmt.format(
                                int(samples[-1]) - int(samples[0])
                            )
                        else:
                            new_stats["selected_delta"] = fmt.format(
                                (samples[-1] - samples[0])
                            )

                    else:
                        new_stats["selected_min"] = "n.a."
                        new_stats["selected_max"] = "n.a."
                        new_stats["selected_average"] = "n.a."
                        new_stats["selected_rms"] = "n.a."
                        new_stats["selected_delta"] = "n.a."

                    sig._stats["range"] = (start, stop)
                    sig._stats["range_stats"] = new_stats

                    stats.update(sig._stats["range_stats"])

                else:
                    stats["selected_start"] = ""
                    stats["selected_stop"] = ""
                    stats["selected_delta_t"] = ""
                    stats["selected_min"] = ""
                    stats["selected_max"] = ""
                    stats["selected_average"] = ""
                    stats["selected_rms"] = ""
                    stats["selected_delta"] = ""

                start, stop = view_region

                #                if sig._stats["visible"] != (start, stop) or sig._stats["fmt"] != fmt:
                new_stats = {}
                new_stats["visible_start"] = start
                new_stats["visible_stop"] = stop
                new_stats["visible_delta_t"] = stop - start

                cut = sig.cut(start, stop)

                if self.mode == "raw":
                    samples = cut.raw_samples
                else:
                    samples = cut.phys_samples

                samples = samples[np.isfinite(samples)]

                if len(samples):
                    kind = samples.dtype.kind
                    format = self.format

                    if kind in "SUV":
                        fmt = "{}"
                    elif kind == "f":
                        fmt = f"{{:.{self.precision}f}}"
                    else:
                        if format == "hex":
                            fmt = "0x{:X}"
                        elif format == "bin":
                            fmt = "0b{:b}"
                        elif format == "phys":
                            fmt = "{}"

                    new_stats["visible_min"] = fmt.format(np.nanmin(samples))
                    new_stats["visible_max"] = fmt.format(np.nanmax(samples))
                    new_stats["visible_average"] = np.mean(samples)
                    new_stats["visible_rms"] = np.sqrt(np.mean(np.square(samples)))
                    if kind in "ui":
                        new_stats["visible_delta"] = int(cut.samples[-1]) - int(
                            cut.samples[0]
                        )
                    else:
                        new_stats["visible_delta"] = fmt.format(
                            cut.samples[-1] - cut.samples[0]
                        )

                else:
                    new_stats["visible_min"] = "n.a."
                    new_stats["visible_max"] = "n.a."
                    new_stats["visible_average"] = "n.a."
                    new_stats["visible_rms"] = "n.a."
                    new_stats["visible_delta"] = "n.a."

                sig._stats["visible"] = (start, stop)
                sig._stats["visible_stats"] = new_stats

                stats.update(sig._stats["visible_stats"])

        else:
            stats["overall_min"] = "n.a."
            stats["overall_max"] = "n.a."
            stats["overall_average"] = "n.a."
            stats["overall_rms"] = "n.a."
            stats["overall_start"] = "n.a."
            stats["overall_stop"] = "n.a."
            stats["unit"] = sig.unit
            stats["color"] = sig.color
            stats["name"] = sig.name

            if cursor is not None:
                position = cursor
                stats["cursor_t"] = position

                stats["cursor_value"] = "n.a."

            else:
                stats["cursor_t"] = ""
                stats["cursor_value"] = ""

            if region is not None:
                start, stop = region

                stats["selected_start"] = start
                stats["selected_stop"] = stop
                stats["selected_delta_t"] = stop - start

                stats["selected_min"] = "n.a."
                stats["selected_max"] = "n.a."
                stats["selected_average"] = "n.a."
                stats["selected_rms"] = "n.a."
                stats["selected_delta"] = "n.a."

            else:
                stats["selected_start"] = ""
                stats["selected_stop"] = ""
                stats["selected_delta_t"] = ""
                stats["selected_min"] = ""
                stats["selected_max"] = ""
                stats["selected_average"] = "n.a."
                stats["selected_rms"] = "n.a."
                stats["selected_delta"] = ""

            start, stop = view_region

            stats["visible_start"] = start
            stats["visible_stop"] = stop
            stats["visible_delta_t"] = stop - start

            stats["visible_min"] = "n.a."
            stats["visible_max"] = "n.a."
            stats["visible_average"] = "n.a."
            stats["visible_rms"] = "n.a."
            stats["visible_delta"] = "n.a."

        #        sig._stats["fmt"] = fmt
        return stats

    def trim(self, start=None, stop=None, width=1900):
        trim_info = (start, stop, width)
        if self.trim_info == trim_info:
            return

        self.trim_info = trim_info
        sig = self
        dim = len(sig.timestamps)

        if dim:

            if start is None:
                start = sig.timestamps[0]
            if stop is None:
                stop = sig.timestamps[-1]

            if self.mode == "raw":
                signal_samples = self.raw_samples
            else:
                signal_samples = self.phys_samples

            start_t, stop_t = (
                sig.timestamps[0],
                sig.timestamps[-1],
            )
            if start > stop_t or stop < start_t:
                sig.plot_samples = signal_samples[:0]
                sig.plot_timestamps = sig.timestamps[:0]
            else:
                start_t = max(start, start_t)
                stop_t = min(stop, stop_t)

                start_ = np.searchsorted(sig.timestamps, start_t, side="right")
                stop_ = np.searchsorted(sig.timestamps, stop_t, side="right")

                try:
                    visible = abs(int((stop_t - start_t) / (stop - start) * width))

                    if visible:
                        raster = abs((stop_ - start_)) // visible
                    else:
                        raster = 0
                except:
                    raster = 0

                while raster > 1:
                    rows = (stop_ - start_) // raster
                    stop_2 = start_ + rows * raster

                    samples = signal_samples[start_:stop_2].reshape(rows, raster)

                    try:
                        pos_max = np.nanargmax(samples, axis=1)
                        pos_min = np.nanargmin(samples, axis=1)
                        break
                    except ValueError:
                        raster -= 1

                if raster > 1:

                    pos = np.dstack([pos_min, pos_max])[0]
                    # pos.sort()
                    pos = np.sort(pos)

                    offsets = np.arange(rows) * raster

                    pos = (pos.T + offsets).T.ravel()

                    samples = signal_samples[start_:stop_2][pos]

                    timestamps = sig.timestamps[start_:stop_2][pos]

                    if stop_2 != stop_:
                        samples_ = signal_samples[stop_2:stop_]

                        pos_max = np.nanargmax(samples_)
                        pos_min = np.nanargmin(samples_)

                        pos = (
                            [pos_min, pos_max]
                            if pos_min < pos_max
                            else [pos_max, pos_min]
                        )

                        samples_ = signal_samples[stop_2:stop_][pos]
                        timestamps_ = sig.timestamps[stop_2:stop_][pos]

                        samples = np.concatenate((samples, samples_))
                        timestamps = np.concatenate((timestamps, timestamps_))

                    sig.plot_samples = samples
                    sig.plot_timestamps = timestamps

                else:
                    start_ = max(0, start_ - 2)
                    stop_ += 2

                    sig.plot_samples = signal_samples[start_:stop_]
                    sig.plot_timestamps = sig.timestamps[start_:stop_]

    def value_at_timestamp(self, stamp):
        cut = self.cut(stamp, stamp)

        if len(self.timestamps) and self.timestamps[-1] < stamp:
            cut.samples = self.samples[-1:]
            cut.phys_samples = self.phys_samples[-1:]
            cut.raw_samples = self.raw_samples[-1:]
            cut.timestamps = self.timestamps[-1:]

        if self.mode == "raw":
            values = cut.raw_samples
        else:
            if self.conversion and hasattr(self.conversion, "text_0"):
                values = self.conversion.convert(cut.samples)
            else:
                values = cut.phys_samples

        if len(values) == 0:
            value = "n.a."
            kind = values.dtype.kind
        else:

            kind = values.dtype.kind
            if kind == "S":
                try:
                    value = values[0].decode("utf-8").strip(" \r\n\t\v\0")
                except:
                    value = values[0].decode("latin-1").strip(" \r\n\t\v\0")

                value = value or "<empty string>"
            else:
                value = values.tolist()[0]

        return value, kind, self.format


class Plot(QtWidgets.QWidget):

    add_channels_request = QtCore.pyqtSignal(list)
    close_request = QtCore.pyqtSignal()
    clicked = QtCore.pyqtSignal()
    cursor_moved_signal = QtCore.pyqtSignal(object, float)
    cursor_removed_signal = QtCore.pyqtSignal(object)
    region_moved_signal = QtCore.pyqtSignal(object, list)
    region_removed_signal = QtCore.pyqtSignal(object)
    show_properties = QtCore.pyqtSignal(list)
    splitter_moved = QtCore.pyqtSignal(object, int)

    def __init__(self, signals, with_dots=False, origin=None, *args, **kwargs):
        events = kwargs.pop("events", None)
        super().__init__(*args, **kwargs)
        self.setContentsMargins(0, 0, 0, 0)
        self.pattern = {}

        self.info_uuid = None

        self._range_start = None
        self._range_stop = None

        self._can_switch_mode = True

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSpacing(1)
        main_layout.setContentsMargins(1, 1, 1, 1)
        # self.setLayout(main_layout)

        vbox = QtWidgets.QVBoxLayout()
        widget = QtWidgets.QWidget()
        self.channel_selection = ListWidget()
        # self.channel_selection.setAlternatingRowColors(False)
        # self.channel_selection.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        hbox = QtWidgets.QHBoxLayout()
        hbox.addWidget(QtWidgets.QLabel("Cursor/Range information"))
        self.cursor_info = QtWidgets.QLabel("")
        self.cursor_info.setTextFormat(QtCore.Qt.RichText)
        self.cursor_info.setAlignment(
            QtCore.Qt.AlignRight | QtCore.Qt.AlignTrailing | QtCore.Qt.AlignVCenter
        )
        hbox.addWidget(self.cursor_info)
        vbox.addLayout(hbox)
        vbox.addWidget(self.channel_selection)
        widget.setLayout(vbox)

        self.splitter = QtWidgets.QSplitter()
        self.splitter.addWidget(widget)
        self.splitter.setOpaqueResize(False)

        self.plot = _Plot(
            with_dots=with_dots, parent=self, events=events, origin=origin
        )

        self.plot.range_modified.connect(self.range_modified)
        self.plot.range_removed.connect(self.range_removed)
        self.plot.range_modified_finished.connect(self.range_modified_finished)
        self.plot.cursor_removed.connect(self.cursor_removed)
        self.plot.cursor_moved.connect(self.cursor_moved)
        self.plot.cursor_move_finished.connect(self.cursor_move_finished)
        self.plot.xrange_changed.connect(self.xrange_changed)
        self.plot.computation_channel_inserted.connect(
            self.computation_channel_inserted
        )
        self.plot.curve_clicked.connect(self.channel_selection.setCurrentRow)

        self.splitter.addWidget(self.plot)

        # self.info = ChannelStats()
        # self.info.hide()
        # self.splitter.addWidget(self.info)

        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setStretchFactor(2, 0)

        self.splitter.splitterMoved.connect(self.set_splitter)

        self.plot.add_channels_request.connect(self.add_channels_request)
        self.setAcceptDrops(True)

        main_layout.addWidget(self.splitter)

        if signals:
            self.add_new_channels(signals)

        self.channel_selection.itemsDeleted.connect(self.channel_selection_reduced)
        self.channel_selection.itemPressed.connect(self.channel_selection_modified)
        self.channel_selection.currentRowChanged.connect(
            self.channel_selection_row_changed
        )
        self.channel_selection.add_channels_request.connect(self.add_channels_request)
        self.channel_selection.set_time_offset.connect(self.plot.set_time_offset)
        self.channel_selection.show_properties.connect(self._show_properties)
        # self.channel_selection.insert_computation.connect(self.plot.insert_computation)

        self.keyboard_events = (
            set(
                [
                    (QtCore.Qt.Key_M, QtCore.Qt.NoModifier),
                    (QtCore.Qt.Key_B, QtCore.Qt.ControlModifier),
                    (QtCore.Qt.Key_H, QtCore.Qt.ControlModifier),
                    (QtCore.Qt.Key_P, QtCore.Qt.ControlModifier),
                ]
            )
            | self.plot.keyboard_events
        )

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)

    def channel_selection_modified(self, item):
        if item:
            uuid = self.channel_selection.itemWidget(item).uuid
            self.info_uuid = uuid

            sig, _ = self.plot.signal_by_uuid(uuid)
            if sig.enable:

                self.plot.set_current_uuid(self.info_uuid)
                if self.info.isVisible():
                    stats = self.plot.get_stats(self.info_uuid)
                    self.info.set_stats(stats)

    def channel_selection_row_changed(self, row):
        if row >= 0:
            item = self.channel_selection.item(row)
            uuid = self.channel_selection.itemWidget(item).uuid
            self.info_uuid = uuid

            sig, _ = self.plot.signal_by_uuid(uuid)
            if sig.enable:

                self.plot.set_current_uuid(self.info_uuid)
                if self.info.isVisible():
                    stats = self.plot.get_stats(self.info_uuid)
                    self.info.set_stats(stats)

    def channel_selection_reduced(self, deleted):

        self.plot.delete_channels(deleted)

        if self.info_uuid in deleted:
            self.info_uuid = None
            self.info.hide()

        rows = self.channel_selection.count()

        if not rows:
            self.close_request.emit()

    def cursor_move_finished(self):
        x = self.plot.timebase
        if x is not None and len(x):
            dim = len(x)
            position = self.plot.cursor1.value()

            right = np.searchsorted(x, position, side="right")
            if right == 0:
                next_pos = x[0]
            elif right == dim:
                next_pos = x[-1]
            else:
                if position - x[right - 1] < x[right] - position:
                    next_pos = x[right - 1]
                else:
                    next_pos = x[right]
            self.plot.cursor1.setPos(next_pos)

        # self.plot.cursor_hint.setData(x=[], y=[])
        self.plot.cursor_hint.hide()

    def cursor_moved(self):
        position = self.plot.cursor1.value()

        x = self.plot.timebase

        if x is not None and len(x):
            dim = len(x)
            position = self.plot.cursor1.value()

            right = np.searchsorted(x, position, side="right")
            if right == 0:
                next_pos = x[0]
            elif right == dim:
                next_pos = x[-1]
            else:
                if position - x[right - 1] < x[right] - position:
                    next_pos = x[right - 1]
                else:
                    next_pos = x[right]

            y = []

            _, (hint_min, hint_max) = self.plot.viewbox.viewRange()

            items = [
                self.channel_selection.item(i)
                for i in range(self.channel_selection.count())
            ]

            uuids = [self.channel_selection.itemWidget(item).uuid for item in items]

            for uuid in uuids:
                sig, idx = self.plot.signal_by_uuid(uuid)

                curve = self.plot.curves[idx]
                viewbox = self.plot.view_boxes[idx]

                if curve.isVisible():
                    index = np.argwhere(sig.timestamps == next_pos).flatten()
                    if len(index):
                        _, (y_min, y_max) = viewbox.viewRange()

                        sample = sig.samples[index[0]]
                        sample = (sample - y_min) / (y_max - y_min) * (
                            hint_max - hint_min
                        ) + hint_min

                        y.append(sample)

            # self.plot.viewbox.setYRange(hint_min, hint_max, padding=0)
            # self.plot.cursor_hint.setData(x=[next_pos] * len(y), y=y)
            # if not self.plot.cursor_hint.isVisible():
            #     self.plot.cursor_hint.show()

        if not self.plot.region:
            fmt = self.plot.x_axis.format
            if fmt == "phys":
                cursor_info_text = f"t = {position:.6f}s"
            elif fmt == "time":
                cursor_info_text = f"t = {timedelta(seconds=position)}"
            elif fmt == "date":
                position_date = self.plot.x_axis.origin + timedelta(seconds=position)
                cursor_info_text = f"t = {position_date}"
            self.cursor_info.setText(cursor_info_text)

            items = [
                self.channel_selection.item(i)
                for i in range(self.channel_selection.count())
            ]

            uuids = [self.channel_selection.itemWidget(item).uuid for item in items]

            for i, uuid in enumerate(uuids):
                signal, idx = self.plot.signal_by_uuid(uuid)
                value, kind, fmt = signal.value_at_timestamp(position)

                item = self.channel_selection.item(i)
                item = self.channel_selection.itemWidget(item)

                item.set_prefix("= ")
                item.kind = kind
                item.set_fmt(fmt)
                item.set_value(value, update=True)

        if self.info.isVisible():
            stats = self.plot.get_stats(self.info_uuid)
            self.info.set_stats(stats)

        self.cursor_moved_signal.emit(self, position)

    def cursor_removed(self):

        for i in range(self.channel_selection.count()):
            item = self.channel_selection.item(i)
            item = self.channel_selection.itemWidget(item)

            if not self.plot.region:
                self.cursor_info.setText("")
                item.set_prefix("")
                item.set_value("")
        if self.info.isVisible():
            stats = self.plot.get_stats(self.info_uuid)
            self.info.set_stats(stats)

        self.cursor_removed_signal.emit(self)

    def range_modified(self):
        start, stop = self.plot.region.getRegion()

        fmt = self.plot.x_axis.format
        if fmt == "phys":
            start_info = f"{start:.6f}s"
            stop_info = f"{stop:.6f}s"
            delta_info = f"{stop - start:.6f}s"
        elif fmt == "time":
            start_info = f"{timedelta(seconds=start)}"
            stop_info = f"{timedelta(seconds=stop)}"
            delta_info = f"{timedelta(seconds=(stop - start))}"
        elif fmt == "date":
            start_info = self.plot.x_axis.origin + timedelta(seconds=start)
            stop_info = self.plot.x_axis.origin + timedelta(seconds=stop)

            delta_info = f"{timedelta(seconds=(stop - start))}"

        self.cursor_info.setText(
            (
                "< html > < head / > < body >"
                f"< p >t1 = {start_info}< / p > "
                f"< p >t2 = {stop_info}< / p > "
                f"< p >Δt = {delta_info}< / p > "
                "< / body > < / html >"
            )
        )

        for i in range(self.channel_selection.count()):

            item = self.channel_selection.item(i)
            item = self.channel_selection.itemWidget(item)

            signal, i = self.plot.signal_by_uuid(item.uuid)

            start_v, kind, fmt = signal.value_at_timestamp(start)
            stop_v, kind, fmt = signal.value_at_timestamp(stop)

            item.set_prefix("Δ = ")
            item.set_fmt(signal.format)

            if "n.a." not in (start_v, stop_v):
                if kind in "ui":
                    delta = np.int64(stop_v) - np.int64(start_v)
                    item.kind = kind
                    item.set_value(delta)
                    item.set_fmt(fmt)
                elif kind == "f":
                    delta = stop_v - start_v
                    item.kind = kind
                    item.set_value(delta)
                    item.set_fmt(fmt)
                else:
                    item.set_value("n.a.")
            else:
                item.set_value("n.a.")

        if self.info.isVisible():
            stats = self.plot.get_stats(self.info_uuid)
            self.info.set_stats(stats)

        self.region_moved_signal.emit(self, [start, stop])

    def xrange_changed(self):
        # if self.info.isVisible():
        #     stats = self.plot.get_stats(self.info_uuid)
        #     self.info.set_stats(stats)
        pass

    def range_modified_finished(self):
        start, stop = self.plot.region.getRegion()

        if self.plot.timebase is not None and len(self.plot.timebase):
            timebase = self.plot.timebase
            dim = len(timebase)

            right = np.searchsorted(timebase, start, side="right")
            if right == 0:
                next_pos = timebase[0]
            elif right == dim:
                next_pos = timebase[-1]
            else:
                if start - timebase[right - 1] < timebase[right] - start:
                    next_pos = timebase[right - 1]
                else:
                    next_pos = timebase[right]
            start = next_pos

            right = np.searchsorted(timebase, stop, side="right")
            if right == 0:
                next_pos = timebase[0]
            elif right == dim:
                next_pos = timebase[-1]
            else:
                if stop - timebase[right - 1] < timebase[right] - stop:
                    next_pos = timebase[right - 1]
                else:
                    next_pos = timebase[right]
            stop = next_pos

            self.plot.region.setRegion((start, stop))

    def keyPressEvent(self, event):
        key = event.key()
        modifiers = event.modifiers()
        if key == QtCore.Qt.Key_M and modifiers == QtCore.Qt.NoModifier:
            ch_size, plt_size, info_size = self.splitter.sizes()

            if self.info.isVisible():
                self.info.hide()
                self.splitter.setSizes((ch_size, plt_size + info_size, 0))

            else:

                self.info.show()
                self.splitter.setSizes(
                    (
                        ch_size,
                        int(0.8 * (plt_size + info_size)),
                        int(0.2 * (plt_size + info_size)),
                    )
                )

        elif (
            key in (QtCore.Qt.Key_B, QtCore.Qt.Key_H, QtCore.Qt.Key_P)
            and modifiers == QtCore.Qt.ControlModifier
        ):
            selected_items = self.channel_selection.selectedItems()
            if not selected_items:
                signals = [(sig, i) for i, sig in enumerate(self.plot.signals)]

            else:
                uuids = [
                    self.channel_selection.itemWidget(item).uuid
                    for item in selected_items
                ]

                signals = [self.plot.signal_by_uuid(uuid) for uuid in uuids]

            if key == QtCore.Qt.Key_B:
                fmt = "bin"
            elif key == QtCore.Qt.Key_H:
                fmt = "hex"
            else:
                fmt = "phys"

            for signal, idx in signals:
                if signal.plot_samples.dtype.kind in "ui":
                    signal.format = fmt
                    if self.plot.current_uuid == signal.uuid:
                        self.plot.y_axis.format = fmt
                        self.plot.y_axis.hide()
                        self.plot.y_axis.show()
            if self.plot.cursor1:
                self.plot.cursor_moved.emit()

        elif (
            key in (QtCore.Qt.Key_R, QtCore.Qt.Key_S)
            and modifiers == QtCore.Qt.AltModifier
            and self._can_switch_mode
        ):
            selected_items = self.channel_selection.selectedItems()
            if not selected_items:
                signals = [(sig, i) for i, sig in enumerate(self.plot.signals)]

            else:
                uuids = [
                    self.channel_selection.itemWidget(item).uuid
                    for item in selected_items
                ]

                signals = [self.plot.signal_by_uuid(uuid) for uuid in uuids]

            if key == QtCore.Qt.Key_R:
                mode = "raw"
            else:
                mode = "phys"

            for signal, idx in signals:
                if signal.mode != mode:

                    view = self.plot.view_boxes[idx]
                    _, (buttom, top) = view.viewRange()

                    try:
                        min_, max_ = float(signal.min), float(signal.max)
                    except:
                        min_, max_ = 0, 1

                    if max_ != min_ and top != buttom:

                        factor = (top - buttom) / (max_ - min_)
                        offset = (buttom - min_) / (top - buttom)
                    else:
                        factor = 1
                        offset = 0

                    signal.mode = mode

                    try:
                        min_, max_ = float(signal.min), float(signal.max)
                    except:
                        min_, max_ = 0, 1

                    if max_ != min_:

                        delta = (max_ - min_) * factor
                        buttom = min_ + offset * delta
                        top = buttom + delta
                    else:
                        buttom, top = max_ - 1, max_ + 1

                    view.setYRange(buttom, top, padding=0, update=True)

                    if self.plot.current_uuid == signal.uuid:
                        self.plot.y_axis.mode = mode
                        self.plot.y_axis.hide()
                        self.plot.y_axis.show()

            self.plot.update_lines(force=True)

            if self.plot.cursor1:
                self.plot.cursor_moved.emit()

        elif key == QtCore.Qt.Key_I and modifiers == QtCore.Qt.ControlModifier:
            if self.plot.cursor1:
                position = self.plot.cursor1.value()
                comment, _ = QtWidgets.QInputDialog.getMultiLineText(
                    self,
                    "Insert comments",
                    f"Enter the comments for cursor position {position:.6f}s:",
                    "",
                )
                line = pg.InfiniteLine(
                    pos=position,
                    label=f"t = {position}s\n\n{comment}",
                    pen={"color": "#FF0000", "width": 2, "style": QtCore.Qt.DashLine},
                    labelOpts={
                        "border": {
                            "color": "#FF0000",
                            "width": 2,
                            "style": QtCore.Qt.DashLine,
                        },
                        "fill": "ff9b37",
                        "color": "#000000",
                        "movable": True,
                    },
                )
                self.plot.plotItem.addItem(line, ignoreBounds=True)

        elif key == QtCore.Qt.Key_I and modifiers == QtCore.Qt.AltModifier:
            visible = None
            for item in self.plot.plotItem.items:
                if not isinstance(item, pg.InfiniteLine) or item is self.plot.cursor1:
                    continue

                if visible is None:
                    visible = item.label.isVisible()

                try:
                    if visible:
                        item.label.setVisible(False)
                    else:
                        item.label.setVisible(True)
                except:
                    pass

        elif (key, modifiers) in self.plot.keyboard_events:
            self.plot.keyPressEvent(event)
        else:
            event.ignore()

    def range_removed(self):
        for i in range(self.channel_selection.count()):
            item = self.channel_selection.item(i)
            item = self.channel_selection.itemWidget(item)

            item.set_prefix("")
            item.set_value("")
            self.cursor_info.setText("")

        self._range_start = None
        self._range_stop = None

        if self.plot.cursor1:
            self.plot.cursor_moved.emit()
        if self.info.isVisible():
            stats = self.plot.get_stats(self.info_uuid)
            self.info.set_stats(stats)

        self.region_removed_signal.emit(self)

    def computation_channel_inserted(self):
        sig = self.plot.signals[-1]

        name, unit = sig.name, sig.unit
        item = ListItem((-1, -1), name, sig.computation, self.channel_selection)
        tooltip = getattr(sig, "tooltip", "")
        it = ChannelDisplay(sig.uuid, unit, sig.samples.dtype.kind, 3, tooltip, self)
        it.setAttribute(QtCore.Qt.WA_StyledBackground)

        font = QtGui.QFont()
        font.setItalic(True)
        it.name.setFont(font)

        it.set_name(name)
        it.set_value("")
        it.set_color(sig.color)
        item.setSizeHint(it.sizeHint())
        self.channel_selection.addItem(item)
        self.channel_selection.setItemWidget(item, it)

        it.color_changed.connect(self.plot.set_color)
        it.enable_changed.connect(self.plot.set_signal_enable)
        it.ylink_changed.connect(self.plot.set_common_axis)

        it.enable_changed.emit(sig.uuid, 1)
        it.enable_changed.emit(sig.uuid, 0)
        it.enable_changed.emit(sig.uuid, 1)

        self.info_uuid = sig.uuid

        self.plot.set_current_uuid(self.info_uuid, True)

    def add_new_channels(self, channels):

        for sig in channels:
            sig.uuid = os.urandom(6).hex()

        invalid = []

        for channel in channels:
            diff = np.diff(channel.timestamps)
            invalid_indexes = np.argwhere(diff <= 0).ravel()
            if len(invalid_indexes):
                invalid_indexes = invalid_indexes[:10] + 1
                idx = invalid_indexes[0]
                ts = channel.timestamps[idx - 1 : idx + 2]
                invalid.append(
                    f"{channel.name} @ index {invalid_indexes[:10] - 1} with first time stamp error: {ts}"
                )

        if invalid:
            errors = "\n".join(invalid)
            QtWidgets.QMessageBox.warning(
                self,
                "The following channels do not have monotonous increasing time stamps:",
                f"The following channels do not have monotonous increasing time stamps:\n{errors}",
            )
            self.plot._can_trim = False

        valid = []
        invalid = []
        for channel in channels:
            if len(channel):
                samples = channel.samples
                if samples.dtype.kind not in "SUV" and np.all(np.isnan(samples)):
                    invalid.append(channel.name)
                elif channel.conversion:
                    samples = channel.physical().samples
                    if samples.dtype.kind not in "SUV" and np.all(np.isnan(samples)):
                        invalid.append(channel.name)
                    else:
                        valid.append(channel)
                else:
                    valid.append(channel)
            else:
                valid.append(channel)

        if invalid:
            QtWidgets.QMessageBox.warning(
                self,
                "All NaN channels will not be plotted:",
                f"The following channels have all NaN samples and will not be plotted:\n{', '.join(invalid)}",
            )

        channels = valid

        channels = self.plot.add_new_channels(channels)

        count = self.channel_selection.count()
        if count:
            for i in range(count):
                wid = self.channel_selection.itemWidget(self.channel_selection.item(i))
                if wid.ylink.checkState() == QtCore.Qt.Unchecked:
                    enforce_y_axis = False
                    break
            else:
                enforce_y_axis = True
        else:
            enforce_y_axis = False

        for sig in channels:

            item = ListItem(
                (sig.group_index, sig.channel_index),
                sig.name,
                sig.computation,
                self.channel_selection,
                sig.mdf_uuid,
            )
            item.setData(QtCore.Qt.UserRole, sig.name)
            tooltip = getattr(sig, "tooltip", "")
            if len(sig.samples) and sig.conversion:
                kind = sig.conversion.convert(sig.samples[:1]).dtype.kind
            else:
                kind = sig.samples.dtype.kind
            it = ChannelDisplay(sig.uuid, sig.unit, kind, 3, tooltip, self)
            it.setAttribute(QtCore.Qt.WA_StyledBackground)

            if sig.computed:
                font = QtGui.QFont()
                font.setItalic(True)
                it.name.setFont(font)

            it.set_name(sig.name)
            it.set_value("")
            it.set_color(sig.color)
            item.setSizeHint(it.sizeHint())
            self.channel_selection.addItem(item)
            self.channel_selection.setItemWidget(item, it)

            it.color_changed.connect(self.plot.set_color)
            it.enable_changed.connect(self.plot.set_signal_enable)
            it.ylink_changed.connect(self.plot.set_common_axis)
            if enforce_y_axis:
                it.ylink.setCheckState(QtCore.Qt.Checked)
            it.individual_axis_changed.connect(self.plot.set_individual_axis)

            self.info_uuid = sig.uuid

    def to_config(self):
        count = self.channel_selection.count()

        channels = []
        for i in range(count):
            channel = {}
            item = self.channel_selection.itemWidget(self.channel_selection.item(i))

            sig, idx = self.plot.signal_by_uuid(item.uuid)

            channel["name"] = sig.name
            channel["unit"] = sig.unit
            channel["enabled"] = item.display.checkState() == QtCore.Qt.Checked
            channel["individual_axis"] = (
                item.individual_axis.checkState() == QtCore.Qt.Checked
            )
            channel["common_axis"] = item.ylink.checkState() == QtCore.Qt.Checked
            channel["color"] = sig.color
            channel["computed"] = sig.computed
            ranges = [
                {"start": start, "stop": stop, "color": color}
                for (start, stop), color in item.ranges.items()
            ]
            channel["ranges"] = ranges

            channel["precision"] = item.precision
            channel["fmt"] = item.fmt
            channel["mode"] = sig.mode
            if sig.computed:
                channel["computation"] = sig.computation

            view = self.plot.view_boxes[idx]
            channel["view_box"] = [
                [float(e) for e in axis] for axis in view.viewRange()
            ]
            channel["mdf_uuid"] = str(sig.mdf_uuid)

            channels.append(channel)

        config = {
            "channels": channels if not self.pattern else [],
            "pattern": self.pattern,
        }

        return config

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat("application/octet-stream-asammdf"):
            e.accept()
        super().dragEnterEvent(e)

    def dropEvent(self, e):
        if e.source() is self.channel_selection:
            super().dropEvent(e)
        else:
            data = e.mimeData()
            if data.hasFormat("application/octet-stream-asammdf"):
                names = extract_mime_names(data)
                self.add_channels_request.emit(names)
            else:
                super().dropEvent(e)

    def widget_by_uuid(self, uuid):
        for i in range(self.channel_selection.count()):
            item = self.channel_selection.item(i)
            widget = self.channel_selection.itemWidget(item)
            if widget.uuid == uuid:
                break
        else:
            widget = None
        return widget

    def _show_properties(self, uuid):
        for sig in self.plot.signals:
            if sig.uuid == uuid:
                if sig.computed:
                    view = ComputedChannelInfoWindow(sig, self)
                    view.show()

                else:
                    self.show_properties.emit(
                        [sig.group_index, sig.channel_index, sig.mdf_uuid]
                    )

    def set_splitter(self, pos, index):
        self.splitter_moved.emit(self, pos)


class _Plot(pg.PlotWidget):
    cursor_moved = QtCore.pyqtSignal()
    cursor_removed = QtCore.pyqtSignal()
    range_removed = QtCore.pyqtSignal()
    range_modified = QtCore.pyqtSignal()
    range_modified_finished = QtCore.pyqtSignal()
    cursor_move_finished = QtCore.pyqtSignal()
    xrange_changed = QtCore.pyqtSignal()
    computation_channel_inserted = QtCore.pyqtSignal()
    curve_clicked = QtCore.pyqtSignal(int)

    add_channels_request = QtCore.pyqtSignal(list)

    def __init__(self, signals=None, with_dots=False, origin=None, *args, **kwargs):
        events = kwargs.pop("events", [])
        super().__init__()

        self._last_update = perf_counter()
        self._can_trim = True

        self.setAcceptDrops(True)

        self._last_size = self.geometry()
        self._settings = QtCore.QSettings()

        self.setContentsMargins(5, 5, 5, 5)
        self.xrange_changed.connect(self.xrange_changed_handle)
        self.with_dots = with_dots
        if self.with_dots:
            self.curvetype = pg.PlotDataItem
        else:
            self.curvetype = pg.PlotCurveItem
        self.info = None
        self.current_uuid = 0

        self.standalone = kwargs.get("standalone", False)

        self.region = None
        self.region_lock = None
        self.cursor1 = None
        self.cursor2 = None
        self.signals = signals or []

        self.axes = []
        self._axes_layout_pos = 2

        self.disabled_keys = set()

        self._timebase_db = {}
        for sig in self.signals:
            uuids = self._timebase_db.setdefault(id(sig.timestamps), set())
            uuids.add(sig.uuid)

        #        self._compute_all_timebase()

        self.showGrid(x=True, y=True)

        self.plot_item = self.plotItem
        self.plot_item.hideAxis("left")
        self.plot_item.hideAxis("bottom")
        self.plotItem.showGrid(x=False, y=False)
        self.layout = self.plot_item.layout
        self.scene_ = self.plot_item.scene()
        self.scene_.sigMouseClicked.connect(self._clicked)
        self.viewbox = self.plot_item.vb

        self.common_axis_items = set()
        self.common_axis_label = ""
        self.common_viewbox = pg.ViewBox(enableMenu=True)
        self.scene_.addItem(self.common_viewbox)
        self.common_viewbox.setXLink(self.viewbox)

        axis = self.layout.itemAt(3, 1)
        axis.setParent(None)
        self.x_axis = FormatedAxis("bottom")
        self.layout.removeItem(self.x_axis)
        self.layout.addItem(self.x_axis, 3, 1)
        self.x_axis.linkToView(axis.linkedView())
        self.plot_item.axes["bottom"]["item"] = self.x_axis
        fmt = self._settings.value("plot_xaxis")
        if fmt == "seconds":
            fmt = "phys"
        self.x_axis.format = fmt
        self.x_axis.origin = origin

        axis = self.layout.itemAt(2, 0)
        axis.setParent(None)
        self.y_axis = FormatedAxis("left")
        self.layout.removeItem(axis)
        self.layout.addItem(self.y_axis, 2, 0)
        self.y_axis.linkToView(axis.linkedView())
        self.plot_item.axes["left"]["item"] = self.y_axis

        self.cursor_hint = pg.PlotDataItem(
            [],
            [],
            pen="#000000",
            symbolBrush="#000000",
            symbolPen="w",
            symbol="s",
            symbolSize=8,
        )
        self.viewbox.addItem(self.cursor_hint)

        self.view_boxes = []
        self.curves = []

        self._prev_geometry = self.viewbox.sceneBoundingRect()

        self.resizeEvent = self._resizeEvent

        self._uuid_map = {}

        self._enabled_changed_signals = []
        self._enable_timer = QtCore.QTimer()
        self._enable_timer.setSingleShot(True)
        self._enable_timer.timeout.connect(self._signals_enabled_changed_handler)

        if signals:
            self.add_new_channels(signals)

        self.viewbox.sigXRangeChanged.connect(self.xrange_changed.emit)

        self.keyboard_events = set(
            [
                (QtCore.Qt.Key_C, QtCore.Qt.NoModifier),
                (QtCore.Qt.Key_F, QtCore.Qt.NoModifier),
                (QtCore.Qt.Key_G, QtCore.Qt.NoModifier),
                (QtCore.Qt.Key_I, QtCore.Qt.NoModifier),
                (QtCore.Qt.Key_O, QtCore.Qt.NoModifier),
                (QtCore.Qt.Key_R, QtCore.Qt.NoModifier),
                (QtCore.Qt.Key_S, QtCore.Qt.ControlModifier),
                (QtCore.Qt.Key_S, QtCore.Qt.NoModifier),
                (QtCore.Qt.Key_Y, QtCore.Qt.NoModifier),
                (QtCore.Qt.Key_Left, QtCore.Qt.NoModifier),
                (QtCore.Qt.Key_Right, QtCore.Qt.NoModifier),
                (QtCore.Qt.Key_H, QtCore.Qt.NoModifier),
                (QtCore.Qt.Key_Insert, QtCore.Qt.NoModifier),
            ]
        )

        events = events or []

        for i, event_info in enumerate(events):
            color = COLORS[len(COLORS) - (i % len(COLORS)) - 1]
            if isinstance(event_info, (list, tuple)):
                to_display = event_info
                labels = [" - Start", " - End"]
            else:
                to_display = [event_info]
                labels = [""]
            for event, label in zip(to_display, labels):
                description = f't = {event["value"]}s'
                if event["description"]:
                    description += f'\n\n{event["description"]}'
                line = pg.InfiniteLine(
                    pos=event["value"],
                    label=f'{event["type"]}{label}\n{description}',
                    pen={"color": color, "width": 2, "style": QtCore.Qt.DashLine},
                    labelOpts={
                        "border": {
                            "color": color,
                            "width": 2,
                            "style": QtCore.Qt.DashLine,
                        },
                        "fill": "#000000",
                        "color": color,
                        "movable": True,
                    },
                )
                self.plotItem.addItem(line, ignoreBounds=True)

        self.viewbox.sigResized.connect(self.update_views)
        if signals:
            self.update_views()

    def update_lines(self, with_dots=None, force=False):
        with_dots_changed = False

        if with_dots is not None and with_dots != self.with_dots:
            self.with_dots = with_dots
            self.curvetype = pg.PlotDataItem if with_dots else pg.PlotCurveItem
            with_dots_changed = True

        if self.curves and (with_dots_changed or force):
            for sig in self.signals:
                _, i = self.signal_by_uuid(sig.uuid)
                color = sig.color
                t = sig.plot_timestamps

                if sig.mode == "raw":
                    style = QtCore.Qt.DashLine
                else:
                    style = QtCore.Qt.SolidLine

                if not force:
                    try:
                        curve = self.curvetype(
                            t,
                            sig.plot_samples,
                            pen={"color": color, "style": style},
                            symbolBrush=color,
                            symbolPen=color,
                            symbol="o",
                            symbolSize=4,
                            clickable=True,
                            mouseWidth=30,
                        )

                        curve.sigClicked.connect(partial(self.curve_clicked.emit, i))
                    except:
                        message = (
                            "Can't show dots due to old pyqtgraph package: "
                            "Please install the latest pyqtgraph from the "
                            "github develop branch\n"
                            "pip install -I --no-deps "
                            "https://github.com/pyqtgraph/pyqtgraph/archive/develop.zip"
                        )
                        logger.warning(message)
                    self.view_boxes[i].removeItem(self.curves[i])

                    self.curves[i] = curve

                    self.view_boxes[i].addItem(curve)
                else:
                    curve = self.curves[i]

                    if len(t):

                        if self.with_dots:
                            #                            curve.setPen({'color': color, 'style': style})
                            pen = pg.fn.mkPen(color=color, style=style)
                            curve.opts["pen"] = pen
                            curve.setData(x=t, y=sig.plot_samples)
                            curve.update()
                        else:
                            curve.invalidateBounds()
                            curve._boundsCache = [
                                [(1, None), (t[0], t[-1])],
                                [(1, None), (sig.min, sig.max)],
                            ]

                            curve.xData = t
                            curve.yData = sig.plot_samples
                            curve.path = None
                            curve.fillPath = None
                            curve._mouseShape = None
                            curve.prepareGeometryChange()
                            curve.informViewBoundsChanged()
                            if curve.opts["pen"].style() != style:
                                curve.opts["pen"].setStyle(style)
                            curve.update()
                #                            curve.sigPlotChanged.emit(curve)

                if sig.enable:
                    curve.show()
                else:
                    curve.hide()

    def set_color(self, uuid, color):
        _, index = self.signal_by_uuid(uuid)
        self.signals[index].color = color
        self.curves[index].setPen(color)
        if self.curvetype == pg.PlotDataItem:
            self.curves[index].setSymbolPen(color)
            self.curves[index].setSymbolBrush(color)

            if self.signals[index].individual_axis:
                self.axes[index].setPen(color)
                self.axes[index].setTextPen(color)

        if uuid == self.current_uuid:
            self.y_axis.setPen(color)
            self.y_axis.setTextPen(color)

    def set_common_axis(self, uuid, state):
        _, index = self.signal_by_uuid(uuid)
        viewbox = self.view_boxes[index]
        if state in (QtCore.Qt.Checked, True, 1):
            viewbox.setYRange(*self.common_viewbox.viewRange()[1], padding=0)
            viewbox.setYLink(self.common_viewbox)
            self.common_axis_items.add(uuid)
        else:
            self.view_boxes[index].setYLink(None)
            self.common_axis_items.remove(uuid)

        self.common_axis_label = ", ".join(
            self.signal_by_uuid(uuid)[0].name for uuid in self.common_axis_items
        )

        self.set_current_uuid(self.current_uuid, True)

    def set_individual_axis(self, uuid, state):

        _, index = self.signal_by_uuid(uuid)

        if state in (QtCore.Qt.Checked, True, 1):
            if self.signals[index].enable:
                self.axes[index].show()
            self.signals[index].individual_axis = True
        else:
            self.axes[index].hide()
            self.signals[index].individual_axis = False

    def set_signal_enable(self, uuid, state):

        sig, index = self.signal_by_uuid(uuid)

        if state in (QtCore.Qt.Checked, True, 1):
            self.signals[index].enable = True
            self.view_boxes[index].setXLink(self.viewbox)
            if self.signals[index].individual_axis:
                self.axes[index].show()

            uuids = self._timebase_db.setdefault(id(sig.timestamps), set())
            uuids.add(sig.uuid)

        else:
            self.signals[index].enable = False
            self.view_boxes[index].setXLink(None)
            self.axes[index].hide()

            try:
                self._timebase_db[id(sig.timestamps)].remove(uuid)

                if len(self._timebase_db[id(sig.timestamps)]) == 0:
                    del self._timebase_db[id(sig.timestamps)]
            except:
                pass

        self._enable_timer.start(50)

    def _signals_enabled_changed_handler(self):
        self._compute_all_timebase()
        self.update_lines(force=True)
        if self.cursor1:
            self.cursor_move_finished.emit()

    def update_views(self):
        geometry = self.viewbox.sceneBoundingRect()
        if geometry != self._prev_geometry:
            for view_box in self.view_boxes:
                view_box.setGeometry(geometry)
            self._prev_geometry = geometry

    def get_stats(self, uuid):
        sig, index = self.signal_by_uuid(uuid)

        return sig.get_stats(
            cursor=self.cursor1.value() if self.cursor1 else None,
            region=self.region.getRegion() if self.region else None,
            view_region=self.viewbox.viewRange()[0],
        )

    def keyPressEvent(self, event):
        key = event.key()
        modifier = event.modifiers()

        if key in self.disabled_keys:
            super().keyPressEvent(event)
        else:

            if key == QtCore.Qt.Key_C and modifier == QtCore.Qt.NoModifier:
                if self.cursor1 is None:
                    start, stop = self.viewbox.viewRange()[0]
                    self.cursor1 = Cursor(pos=0, angle=90, movable=True)
                    self.plotItem.addItem(self.cursor1, ignoreBounds=True)
                    self.cursor1.sigPositionChanged.connect(self.cursor_moved.emit)
                    self.cursor1.sigPositionChangeFinished.connect(
                        self.cursor_move_finished.emit
                    )
                    self.cursor1.setPos((start + stop) / 2)
                    self.cursor_move_finished.emit()

                    if self.region is not None:
                        self.cursor1.hide()

                else:
                    self.plotItem.removeItem(self.cursor1)
                    self.cursor1.setParent(None)
                    self.cursor1 = None
                    self.cursor_removed.emit()

            elif key == QtCore.Qt.Key_Y and modifier == QtCore.Qt.NoModifier:
                if self.region is not None:
                    if self.region_lock is not None:
                        self.region_lock = None
                    else:
                        self.region_lock = self.region.getRegion()[0]
                else:
                    self.region_lock = None

            elif key == QtCore.Qt.Key_X and modifier == QtCore.Qt.NoModifier:
                if self.region is not None:
                    self.viewbox.setXRange(*self.region.getRegion(), padding=0)
                    event_ = QtGui.QKeyEvent(
                        QtCore.QEvent.KeyPress, QtCore.Qt.Key_R, QtCore.Qt.NoModifier
                    )
                    self.keyPressEvent(event_)

            elif key == QtCore.Qt.Key_F and modifier == QtCore.Qt.NoModifier:
                if self.common_axis_items:
                    if any(
                        len(self.signal_by_uuid(uuid)[0].plot_samples)
                        for uuid in self.common_axis_items
                        if self.signal_by_uuid(uuid)[0].enable
                    ):
                        with_common_axis = True

                        common_min = np.nanmin(
                            [
                                np.nanmin(self.signal_by_uuid(uuid)[0].plot_samples)
                                for uuid in self.common_axis_items
                                if len(self.signal_by_uuid(uuid)[0].plot_samples)
                            ]
                        )
                        common_max = np.nanmax(
                            [
                                np.nanmax(self.signal_by_uuid(uuid)[0].plot_samples)
                                for uuid in self.common_axis_items
                                if len(self.signal_by_uuid(uuid)[0].plot_samples)
                            ]
                        )
                    else:
                        with_common_axis = False

                for i, (viewbox, signal) in enumerate(
                    zip(self.view_boxes, self.signals)
                ):
                    if len(signal.plot_samples):
                        if signal.uuid in self.common_axis_items:
                            if with_common_axis:
                                min_ = common_min
                                max_ = common_max
                                with_common_axis = False
                            else:
                                continue
                        else:
                            samples = signal.plot_samples[
                                np.isfinite(signal.plot_samples)
                            ]
                            if len(samples):
                                min_, max_ = (
                                    np.nanmin(samples),
                                    np.nanmax(samples),
                                )
                            else:
                                min_, max_ = 0, 1
                        if min_ != min_:
                            min_ = 0
                        if max_ != max_:
                            max_ = 1

                        viewbox.setYRange(min_, max_, padding=0)

                if self.cursor1:
                    self.cursor_moved.emit()

            elif key == QtCore.Qt.Key_G and modifier == QtCore.Qt.NoModifier:
                y = self.plotItem.ctrl.yGridCheck.isChecked()
                x = self.plotItem.ctrl.xGridCheck.isChecked()

                if x and y:
                    self.plotItem.showGrid(x=False, y=False)
                elif x:
                    self.plotItem.showGrid(x=True, y=True)
                else:
                    self.plotItem.showGrid(x=True, y=False)

            elif (
                key in (QtCore.Qt.Key_I, QtCore.Qt.Key_O)
                and modifier == QtCore.Qt.NoModifier
            ):
                x_range, _ = self.viewbox.viewRange()
                delta = x_range[1] - x_range[0]
                step = delta * 0.05
                if key == QtCore.Qt.Key_I:
                    step = -step
                if self.cursor1:
                    pos = self.cursor1.value()
                    x_range = pos - delta / 2, pos + delta / 2
                self.viewbox.setXRange(x_range[0] - step, x_range[1] + step, padding=0)

            elif key == QtCore.Qt.Key_R and modifier == QtCore.Qt.NoModifier:
                if self.region is None:

                    self.region = pg.LinearRegionItem((0, 0))
                    self.region.setZValue(-10)
                    self.plotItem.addItem(self.region)
                    self.region.sigRegionChanged.connect(self.range_modified.emit)
                    self.region.sigRegionChangeFinished.connect(
                        self.range_modified_finished.emit
                    )
                    for line in self.region.lines:
                        line.addMarker("^", 0)
                        line.addMarker("v", 1)
                    start, stop = self.viewbox.viewRange()[0]
                    start, stop = (
                        start + 0.1 * (stop - start),
                        stop - 0.1 * (stop - start),
                    )
                    self.region.setRegion((start, stop))

                    if self.cursor1 is not None:
                        self.cursor1.hide()

                else:
                    self.region_lock = None
                    self.region.setParent(None)
                    self.region.hide()
                    self.region = None
                    self.range_removed.emit()

                    if self.cursor1 is not None:
                        self.cursor1.show()

            elif key == QtCore.Qt.Key_S and modifier == QtCore.Qt.ControlModifier:
                file_name, _ = QtWidgets.QFileDialog.getSaveFileName(
                    self,
                    "Select output measurement file",
                    "",
                    "MDF version 4 files (*.mf4)",
                )

                if file_name:
                    signals = [signal for signal in self.signals if signal.enable]
                    if signals:
                        with MDF() as mdf:
                            groups = {}
                            for sig in signals:
                                id_ = id(sig.timestamps)
                                group_ = groups.setdefault(id_, [])
                                group_.append(sig)

                            for signals in groups.values():
                                sigs = []
                                for signal in signals:
                                    if ":" in signal.name:
                                        sig = signal.copy()
                                        sig.name = sig.name.split(":")[-1].strip()
                                        sigs.append(sig)
                                    else:
                                        sigs.append(signal)
                                mdf.append(sigs, common_timebase=True)
                            mdf.save(file_name, overwrite=True)

            elif key == QtCore.Qt.Key_S and modifier == QtCore.Qt.NoModifier:

                parent = self.parent().parent()
                count = parent.channel_selection.count()
                uuids = []

                for i in range(count):
                    item = parent.channel_selection.item(i)
                    uuids.append(parent.channel_selection.itemWidget(item).uuid)
                uuids = reversed(uuids)

                count = sum(
                    1
                    for i, (sig, curve) in enumerate(zip(self.signals, self.curves))
                    if sig.min != "n.a."
                    and curve.isVisible()
                    and sig.uuid not in self.common_axis_items
                )

                if any(
                    sig.min != "n.a."
                    and curve.isVisible()
                    and sig.uuid in self.common_axis_items
                    for (sig, curve) in zip(self.signals, self.curves)
                ):
                    count += 1
                    with_common_axis = True
                else:
                    with_common_axis = False

                if count:

                    position = 0
                    for uuid in uuids:
                        signal, index = self.signal_by_uuid(uuid)
                        viewbox = self.view_boxes[index]

                        if not signal.empty and signal.enable:
                            if (
                                with_common_axis
                                and signal.uuid in self.common_axis_items
                            ):
                                with_common_axis = False

                                min_ = np.nanmin(
                                    [
                                        np.nanmin(
                                            self.signal_by_uuid(uuid)[0].plot_samples
                                        )
                                        for uuid in self.common_axis_items
                                        if len(
                                            self.signal_by_uuid(uuid)[0].plot_samples
                                        )
                                        and self.signal_by_uuid(uuid)[0].enable
                                    ]
                                )
                                max_ = np.nanmax(
                                    [
                                        np.nanmax(
                                            self.signal_by_uuid(uuid)[0].plot_samples
                                        )
                                        for uuid in self.common_axis_items
                                        if len(
                                            self.signal_by_uuid(uuid)[0].plot_samples
                                        )
                                        and self.signal_by_uuid(uuid)[0].enable
                                    ]
                                )

                            else:
                                if signal.uuid in self.common_axis_items:
                                    continue
                                min_ = signal.min
                                max_ = signal.max

                            if min_ == -float("inf") and max_ == float("inf"):
                                min_ = 0
                                max_ = 1
                            elif min_ == -float("inf"):
                                min_ = max_ - 1
                            elif max_ == float("inf"):
                                max_ = min_ + 1

                            if min_ == max_:
                                min_, max_ = min_ - 1, max_ + 1

                            dim = (float(max_) - min_) * 1.1

                            max_ = min_ + dim * count - 0.05 * dim
                            min_ = min_ - 0.05 * dim

                            min_, max_ = (
                                min_ - dim * position,
                                max_ - dim * position,
                            )

                            viewbox.setYRange(min_, max_, padding=0)

                            position += 1

                else:
                    xrange, _ = self.viewbox.viewRange()
                    self.viewbox.autoRange(padding=0)
                    self.viewbox.setXRange(*xrange, padding=0)
                    self.viewbox.disableAutoRange()
                if self.cursor1:
                    self.cursor_moved.emit()

            elif (
                key in (QtCore.Qt.Key_Left, QtCore.Qt.Key_Right)
                and modifier == QtCore.Qt.NoModifier
            ):
                if self.cursor1:
                    prev_pos = pos = self.cursor1.value()
                    dim = len(self.timebase)
                    if dim:
                        pos = np.searchsorted(self.timebase, pos)
                        if key == QtCore.Qt.Key_Right:
                            pos += 1
                        else:
                            pos -= 1
                        pos = np.clip(pos, 0, dim - 1)
                        pos = self.timebase[pos]
                    else:
                        if key == QtCore.Qt.Key_Right:
                            pos += 1
                        else:
                            pos -= 1

                    (left_side, right_side), _ = self.viewbox.viewRange()

                    if pos >= right_side:
                        delta = abs(pos - prev_pos)
                        self.viewbox.setXRange(
                            left_side + delta, right_side + delta, padding=0
                        )
                    elif pos <= left_side:
                        delta = abs(pos - prev_pos)
                        self.viewbox.setXRange(
                            left_side - delta, right_side - delta, padding=0
                        )
                    else:
                        delta = 0

                    self.cursor1.set_value(pos)

            elif key == QtCore.Qt.Key_H and modifier == QtCore.Qt.NoModifier:
                if len(self.all_timebase):
                    start_ts = np.amin(self.all_timebase)
                    stop_ts = np.amax(self.all_timebase)

                    self.viewbox.setXRange(start_ts, stop_ts)
                    event_ = QtGui.QKeyEvent(
                        QtCore.QEvent.KeyPress, QtCore.Qt.Key_F, QtCore.Qt.NoModifier
                    )
                    self.keyPressEvent(event_)

                    if self.cursor1:
                        self.cursor_moved.emit()

            elif key == QtCore.Qt.Key_Insert and modifier == QtCore.Qt.NoModifier:
                self.insert_computation()

            else:
                self.parent().keyPressEvent(event)

    def trim(self, signals=None):
        signals = signals or self.signals
        if not self._can_trim:
            return
        (start, stop), _ = self.viewbox.viewRange()

        width = self.width() - self.y_axis.width()

        for sig in signals:
            sig.trim(start, stop, width)

    def xrange_changed_handle(self):
        self.trim()
        self.update_lines(force=True)

    def _resizeEvent(self, ev):

        new_size, last_size = self.geometry(), self._last_size
        if new_size != last_size:
            self._last_size = new_size
            self.xrange_changed_handle()
            super().resizeEvent(ev)

    def set_current_uuid(self, uuid, force=False):
        axis = self.y_axis
        viewbox = self.viewbox

        sig, index = self.signal_by_uuid(uuid)

        if sig.conversion and hasattr(sig.conversion, "text_0"):
            axis.text_conversion = sig.conversion
        else:
            axis.text_conversion = None
        axis.format = sig.format

        if uuid in self.common_axis_items:
            if self.current_uuid not in self.common_axis_items or force:
                for sig_, vbox in zip(self.signals, self.view_boxes):
                    if sig_.uuid not in self.common_axis_items:
                        vbox.setYLink(None)

                vbox = self.view_boxes[index]
                viewbox.setYRange(*vbox.viewRange()[1], padding=0)
                self.common_viewbox.setYRange(*vbox.viewRange()[1], padding=0)
                self.common_viewbox.setYLink(viewbox)

                if self._settings.value("plot_background") == "Black":
                    axis.setPen("#FFFFFF")
                    axis.setTextPen("#FFFFFF")
                else:
                    axis.setPen("#000000")
                    axis.setTextPen("#000000")
                axis.setLabel(self.common_axis_label)

        else:
            self.common_viewbox.setYLink(None)
            for sig_, vbox in zip(self.signals, self.view_boxes):
                if sig_.uuid not in self.common_axis_items:
                    vbox.setYLink(None)

            viewbox.setYRange(*self.view_boxes[index].viewRange()[1], padding=0)
            self.view_boxes[index].setYLink(viewbox)
            if len(sig.name) <= 32:
                if sig.unit:
                    axis.setLabel(f"{sig.name} [{sig.unit}]")
                else:
                    axis.setLabel(f"{sig.name}")
            else:
                if sig.unit:
                    axis.setLabel(f"{sig.name[:29]}...  [{sig.unit}]")
                else:
                    axis.setLabel(f"{sig.name[:29]}...")

            axis.setPen(sig.color)
            axis.setTextPen(sig.color)
            axis.update()

        self.current_uuid = uuid
        axis.setWidth()

    def _clicked(self, event):
        modifiers = QtGui.QApplication.keyboardModifiers()

        if QtCore.Qt.Key_C not in self.disabled_keys:

            if self.region is None:
                pos = self.plot_item.vb.mapSceneToView(event.scenePos())

                if self.cursor1 is not None:
                    self.plotItem.removeItem(self.cursor1)
                    self.cursor1.setParent(None)
                    self.cursor1 = None

                self.cursor1 = Cursor(pos=pos, angle=90, movable=True)
                self.plotItem.addItem(self.cursor1, ignoreBounds=True)
                self.cursor1.sigPositionChanged.connect(self.cursor_moved.emit)
                self.cursor1.sigPositionChangeFinished.connect(
                    self.cursor_move_finished.emit
                )
                self.cursor_move_finished.emit()

            else:
                pos = self.plot_item.vb.mapSceneToView(event.scenePos())
                start, stop = self.region.getRegion()

                if self.region_lock is not None:
                    self.region.setRegion((self.region_lock, pos.x()))
                else:
                    if modifiers == QtCore.Qt.ControlModifier:
                        self.region.setRegion((start, pos.x()))
                    else:
                        self.region.setRegion((pos.x(), stop))

    def add_new_channels(self, channels, computed=False):
        geometry = self.viewbox.sceneBoundingRect()
        initial_index = len(self.signals)

        for sig in channels:
            if not hasattr(sig, "computed"):
                sig.computed = computed
                if not computed:
                    sig.computation = {}

        (start, stop), _ = self.viewbox.viewRange()

        width = self.width() - self.y_axis.width()
        trim_info = start, stop, width

        channels = [
            PlotSignal(sig, i, trim_info=trim_info)
            for i, sig in enumerate(channels, len(self.signals))
        ]

        for sig in channels:
            uuids = self._timebase_db.setdefault(id(sig.timestamps), set())
            uuids.add(sig.uuid)
        self.signals.extend(channels)

        self._uuid_map = {sig.uuid: (sig, i) for i, sig in enumerate(self.signals)}

        self._compute_all_timebase()

        if initial_index == 0 and len(self.all_timebase):
            start_t, stop_t = np.amin(self.all_timebase), np.amax(self.all_timebase)
            self.viewbox.setXRange(start_t, stop_t)

        axis_uuid = None

        for index, sig in enumerate(channels, initial_index):
            color = sig.color

            axis = FormatedAxis(
                "right",
                pen=color,
                textPen=color,
                text=sig.name if len(sig.name) <= 32 else "{sig.name[:29]}...",
                units=sig.unit,
            )
            if sig.conversion and hasattr(sig.conversion, "text_0"):
                axis.text_conversion = sig.conversion

            view_box = pg.ViewBox(enableMenu=False)
            view_box.setGeometry(geometry)
            view_box.disableAutoRange()

            axis.linkToView(view_box)
            #            if len(sig.name) <= 32:
            #                axis.labelText = sig.name
            #            else:
            #                axis.labelText = f"{sig.name[:29]}..."
            #            axis.labelUnits = sig.unit
            #            axis.labelStyle = {"color": color}
            #
            #            axis.setLabel(axis.labelText, sig.unit, color=color)

            self.layout.addItem(axis, 2, self._axes_layout_pos)
            self._axes_layout_pos += 1

            self.scene_.addItem(view_box)

            t = sig.plot_timestamps

            curve = self.curvetype(
                t,
                sig.plot_samples,
                pen=color,
                symbolBrush=color,
                symbolPen=color,
                symbol="o",
                symbolSize=4,
                clickable=True,
                mouseWidth=30,
                #                connect='finite',
            )
            curve.hide()

            curve.sigClicked.connect(partial(self.curve_clicked.emit, index))

            self.view_boxes.append(view_box)
            self.curves.append(curve)
            if not sig.empty:
                view_box.setYRange(sig.min, sig.max, padding=0, update=True)

            #            (start, stop), _ = self.viewbox.viewRange()
            #            view_box.setXRange(start, stop, padding=0, update=True)

            self.axes.append(axis)
            axis.hide()
            view_box.addItem(curve)

            if initial_index == 0 and index == 0:
                axis_uuid = sig.uuid

        for index, sig in enumerate(channels, initial_index):
            self.view_boxes[index].setXLink(self.viewbox)

        for curve in self.curves[initial_index:]:
            curve.show()

        if axis_uuid is not None:
            self.set_current_uuid(sig.uuid)

        return channels

    def _compute_all_timebase(self):
        if self._timebase_db:
            timebases = [
                sig.timestamps
                for sig in self.signals
                if id(sig.timestamps) in self._timebase_db
            ]
            try:
                new_timebase = np.unique(np.concatenate(timebases))
            except MemoryError:
                new_timebase = reduce(np.union1d, timebases)
            self.all_timebase = self.timebase = new_timebase
        else:
            self.all_timebase = self.timebase = []

    def signal_by_uuid(self, uuid):
        return self._uuid_map[uuid]

        raise Exception("Signal not found")

    def signal_by_name(self, name):
        for i, sig in enumerate(self.signals):
            if sig.name == name:
                return sig, i

        raise Exception(
            f"Signal not found: {name} {[sig.name for sig in self.signals]}"
        )

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat("application/octet-stream-asammdf"):
            e.accept()
        super().dragEnterEvent(e)

    def dropEvent(self, e):
        if e.source() is self.parent().channel_selection:
            super().dropEvent(e)
        else:
            data = e.mimeData()
            if data.hasFormat("application/octet-stream-asammdf"):
                names = extract_mime_names(data)
                self.add_channels_request.emit(names)
            else:
                super().dropEvent(e)

    def delete_channels(self, deleted):

        needs_timebase_compute = False

        indexes = sorted(
            [(self.signal_by_uuid(uuid)[1], uuid) for uuid in deleted], reverse=True
        )

        for i, uuid in indexes:
            item = self.curves.pop(i)
            item.hide()
            item.setParent(None)
            self.view_boxes[i].removeItem(item)

            item = self.axes.pop(i)
            item.unlinkFromView()
            self.layout.removeItem(item)
            item.hide()
            item.setParent(None)

            item = self.view_boxes.pop(i)
            self.layout.removeItem(item)
            self.scene_.removeItem(item)
            item.hide()
            item.setParent(None)
            item.setXLink(None)
            item.setYLink(None)

            sig = self.signals.pop(i)

            if uuid in self.common_axis_items:
                self.common_axis_items.remove(uuid)

            if sig.enable:
                self._timebase_db[id(sig.timestamps)].remove(sig.uuid)

                if len(self._timebase_db[id(sig.timestamps)]) == 0:
                    del self._timebase_db[id(sig.timestamps)]
                    needs_timebase_compute = True

        uuids = [sig.uuid for sig in self.signals]

        self._uuid_map = {sig.uuid: (sig, i) for i, sig in enumerate(self.signals)}

        if uuids:
            if self.current_uuid in uuids:
                self.set_current_uuid(self.current_uuid, True)
            else:
                self.set_current_uuid(uuids[0], True)
        else:
            self.current_uuid = None

        if needs_timebase_compute:
            self._compute_all_timebase()

    def set_time_offset(self, info):
        absolute, offset, *uuids = info

        signals = [sig for sig in self.signals if sig.uuid in uuids]

        if absolute:
            for sig in signals:
                if not len(sig.timestamps):
                    continue
                id_ = id(sig.timestamps)
                delta = sig.timestamps[0] - offset
                sig.timestamps = sig.timestamps - delta

                uuids = self._timebase_db.setdefault(id(sig.timestamps), set())
                uuids.add(sig.uuid)

                self._timebase_db[id_].remove(sig.uuid)
                if len(self._timebase_db[id_]) == 0:
                    del self._timebase_db[id_]
        else:
            for sig in signals:
                if not len(sig.timestamps):
                    continue
                id_ = id(sig.timestamps)

                sig.timestamps = sig.timestamps + offset

                uuids = self._timebase_db.setdefault(id(sig.timestamps), set())
                uuids.add(sig.uuid)

                self._timebase_db[id_].remove(sig.uuid)
                if len(self._timebase_db[id_]) == 0:
                    del self._timebase_db[id_]

        self.xrange_changed_handle()

        self._compute_all_timebase()

        self.xrange_changed_handle()

    def insert_computation(self, name=""):
        dlg = DefineChannel(self.signals, self.all_timebase, name, self)
        dlg.setModal(True)
        dlg.exec_()
        sig = dlg.result

        if sig is not None:
            sig.uuid = os.urandom(6).hex()
            sig.mdf_uuid = os.urandom(6).hex()
            self.add_new_channels([sig], computed=True)
            self.computation_channel_inserted.emit()
