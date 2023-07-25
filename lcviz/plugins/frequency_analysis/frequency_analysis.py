from functools import cached_property
from traitlets import Bool, Float, List, Unicode, observe

from lightkurve import periodogram

from jdaviz.core.custom_traitlets import FloatHandleEmpty
from jdaviz.core.registries import tray_registry
from jdaviz.core.template_mixin import (PluginTemplateMixin,
                                        DatasetSelectMixin, SelectPluginComponent, PlotMixin)
from jdaviz.core.user_api import PluginUserApi

from lcviz.utils import data_not_folded


__all__ = ['FrequencyAnalysis']


@tray_registry('frequency-analysis', label="Frequency Analysis")
class FrequencyAnalysis(PluginTemplateMixin, DatasetSelectMixin, PlotMixin):
    """
    See the :ref:`Frequency Analysis Plugin Documentation <frequency_analysis>` for more details.

    Only the following attributes and methods are available through the
    public plugin API.

    * ``dataset`` (:class:`~jdaviz.core.template_mixin.DatasetSelect`):
      Dataset to use for analysis.
    * ``method`` (:class:`~jdaviz.core.template_mixing.SelectPluginComponent`):
      Method/algorithm to determine the period.
    * ``xunit`` (:class:`~jdaviz.core.template_mixing.SelectPluginComponent`):
      Whether to plot power vs fequency or period.
    * ``auto_range``
    * ``minimum``
    * ``maximum``
    * :meth:``periodogram``
    """
    template_file = __file__, "frequency_analysis.vue"

    method_items = List().tag(sync=True)
    method_selected = Unicode().tag(sync=True)

    xunit_items = List().tag(sync=True)
    xunit_selected = Unicode().tag(sync=True)

    auto_range = Bool(True).tag(sync=True)
    minimum = FloatHandleEmpty(0.1).tag(sync=True)  # frequency
    minimum_step = Float(0.1).tag(sync=True)
    maximum = FloatHandleEmpty(1).tag(sync=True)  # frequency
    maximum_step = Float(0.1).tag(sync=True)

    spinner = Bool().tag(sync=True)
    err = Unicode().tag(sync=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._ignore_auto_update = False

        # do not support data only in phase-space
        self.dataset.add_filter(data_not_folded)

        self.method = SelectPluginComponent(self,
                                            items='method_items',
                                            selected='method_selected',
                                            manual_options=['Lomb-Scargle', 'Box Least Squares'])

        self.xunit = SelectPluginComponent(self,
                                           items='xunit_items',
                                           selected='xunit_selected',
                                           manual_options=['frequency', 'period'])

        self.plot.add_line('line', color='gray', marker_size=12)
        self.plot.figure.axes[1].label = 'power'
        self._update_xunit()

    # TODO: remove if/once inherited from jdaviz
    # (https://github.com/spacetelescope/jdaviz/pull/2253)
    def _clear_cache(self, *attrs):
        """
        provide convenience function to clearing the cache for cached_properties
        """
        if not len(attrs):
            attrs = self._cached_properties
        for attr in attrs:
            if attr in self.__dict__:
                del self.__dict__[attr]

    @property
    def user_api(self):
        expose = ['dataset', 'method', 'xunit', 'auto_range', 'minimum', 'maximum', 'periodogram']
        return PluginUserApi(self, expose=expose)

    @cached_property
    def periodogram(self):
        # TODO: support multiselect on self.dataset and combine light curves (or would that be a
        # dedicated plugin of its own)?
        self.spinner = True
        self.err = ''
        if self.auto_range:
            min_period, max_period = None, None
        elif self.xunit_selected == 'period':
            min_period, max_period = self.minimum, self.maximum
        else:
            min_period, max_period = self.maximum ** -1, self.minimum ** -1
        if self.method == 'Box Least Squares':
            try:
                per = periodogram.BoxLeastSquaresPeriodogram.from_lightcurve(self.dataset.selected_obj,  # noqa
                                                                             minimum_period=min_period,  # noqa
                                                                             maximum_period=max_period)  # noqa
            except Exception as err:
                self.spinner = False
                self.err = str(err)
                self.plot.clear_all_marks()
                return None
        elif self.method == 'Lomb-Scargle':
            try:
                per = periodogram.LombScarglePeriodogram.from_lightcurve(self.dataset.selected_obj,
                                                                         minimum_period=min_period,
                                                                         maximum_period=max_period)
            except Exception as err:
                self.spinner = False
                self.err = str(err)
                self.plot.clear_all_marks()
                return None
        else:
            self.spinner = False
            raise NotImplementedError(f"periodogram not implemented for {self.method}")

        self._update_periodogram_labels(per)
        self.spinner = False
        return per

    @observe('xunit_selected')
    def _update_xunit(self, *args):
        per = self.periodogram
        if per is not None:
            self.plot.marks['line'].x = getattr(per, self.xunit_selected)
        else:
            self.plot.clear_all_marks()

        self._update_periodogram_labels(per)

        # convert minimum/maximum for next computation
        self._ignore_auto_update = True
        old_min, old_max = self.minimum, self.maximum
        self.minimum = old_max ** -1 if old_max > 0 else 0
        self.maximum = old_min ** -1 if old_min > 0 else 0
        self._ignore_auto_update = False

    def _update_periodogram_labels(self, per=None):
        per = per if per is not None else self.periodogram
        if per is not None:
            self.plot.figure.axes[0].label = f"{self.xunit_selected} ({getattr(per, self.xunit_selected).unit})"  # noqa
            self.plot.figure.axes[1].label = f"power ({per.power.unit})" if per.power.unit != "" else "power"  # noqa
        else:
            self.plot.figure.axes[0].label = self.xunit_selected
            self.plot.figure.axes[1].label = "power"

    @observe('dataset_selected', 'method_selected', 'auto_range', 'minimum', 'maximum')
    def _update_periodogram(self, *args):
        if not (hasattr(self, 'method') and hasattr(self, 'dataset')):
            return
        if self._ignore_auto_update:
            return

        # TODO: avoid clearing cache if change was to min/max but auto_range is True?
        self._clear_cache('periodogram')

        per = self.periodogram
        if per is not None:
            line = self.plot.marks['line']
            line.x, line.y = getattr(per, self.xunit_selected), per.power
            self._update_periodogram_labels(per)
        else:
            self.plot.clear_all_marks()
