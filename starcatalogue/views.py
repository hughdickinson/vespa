from astropy.coordinates import SkyCoord
from astropy.coordinates.name_resolve import NameResolveError
from astropy import units as u

from celery.result import AsyncResult

from django.conf import settings
from django.db.models import Q, F
from django.http import HttpResponseRedirect, HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.generic.base import TemplateView
from django.views.generic.list import ListView
from django.views.generic import DetailView
from django.views import View

from starcatalogue.models import Star, FoldedLightcurve, DataExport
from starcatalogue.fields import Distance


class StarListView(ListView):
    paginate_by = 20

    def get_queryset(self, params=None):
        if params is None:
            params = self.request.GET

        qs = FoldedLightcurve.objects.all()

        try:
            self.min_period = float(params.get('min_period', None))
            if self.min_period:
                qs = qs.filter(period_length__gte=self.min_period)
            else:
                # To ensure it's None rather than ''
                self.min_period = None
        except (ValueError, TypeError):
            self.min_period = None
        
        try:
            self.max_period = float(params.get('max_period', None))
            if self.max_period:
                qs = qs.filter(period_length__lte=self.max_period)
            else:
                # To ensure it's None rather than ''
                self.max_period = None
        except (ValueError, TypeError):
            self.max_period = None

        self.certain_period = params.get('certain_period', 'off')
        self.uncertain_period = params.get('uncertain_period', 'off')

        uncertainty_map = {
            FoldedLightcurve.CERTAIN: self.certain_period,
            FoldedLightcurve.UNCERTAIN: self.uncertain_period,
        }

        enabled_uncertainties = [ k for k, v in uncertainty_map.items() if v == 'on']

        if not enabled_uncertainties:
            enabled_uncertainties = uncertainty_map.keys()
            self.certain_period = 'on'
            self.uncertain_period = 'on'

        qs = qs.filter(period_uncertainty__in=enabled_uncertainties)

        try:
            self.min_magnitude = float(params.get('min_magnitude', None))
            if self.min_magnitude:
                qs = qs.filter(star___mean_magnitude__gte=self.min_magnitude)
            else:
                # To ensure it's None rather than ''
                self.min_magnitude = None
        except (ValueError, TypeError):
            self.min_magnitude = None
        
        try:
            self.max_magnitude = float(params.get('max_magnitude', None))
            if self.max_magnitude:
                qs = qs.filter(star___mean_magnitude__lte=self.max_magnitude)
            else:
                # To ensure it's None rather than ''
                self.max_magnitude = None
        except (ValueError, TypeError):
            self.max_magnitude = None

        self.type_pulsator = params.get('type_pulsator', 'off')
        self.type_rotator = params.get('type_rotator', 'off')
        self.type_ew = params.get('type_ew', 'off')
        self.type_eaeb = params.get('type_eaeb', 'off')
        self.type_unknown = params.get('type_unknown', 'off')

        type_map = {
            FoldedLightcurve.PULSATOR: self.type_pulsator,
            FoldedLightcurve.EA_EB: self.type_eaeb,
            FoldedLightcurve.EW: self.type_ew,
            FoldedLightcurve.ROTATOR: self.type_rotator,
            FoldedLightcurve.UNKNOWN: self.type_unknown,
        }

        enabled_types = [ k for k, v in type_map.items() if v == 'on']

        # If nothing is enabled, enable everything
        # This works as a default, because why would anyone actually want to exclude all types?
        if not enabled_types:
            enabled_types = type_map.keys()
            self.type_pulsator = 'on'
            self.type_rotator = 'on'
            self.type_ew = 'on'
            self.type_eaeb = 'on'
            self.type_unknown = 'on'

        qs = qs.filter(classification__in=enabled_types)

        self.search = params.get('search', None)
        self.search_radius = params.get('search_radius', None)
        self.coords = None

        if self.search:
            try:
               self.search_radius = float(self.search_radius)
            except (ValueError, TypeError):
               self.search_radius = 0.1

            if self.search_radius < 0:
                self.search_radius = 0
            if self.search_radius > 90:
                self.search_radius = 90

            if self.search.startswith('1SWASP'):
                try:
                    self.coords = Star.objects.get(superwasp_id=self.search).coords
                except Star.DoesNotExist:
                    pass
            
            if self.coords is None:
                try:
                    self.coords = SkyCoord(self.search)
                except ValueError:
                    try:
                        self.coords = SkyCoord.from_name(self.search, parse=True)
                    except NameResolveError:
                        pass
                
            if self.coords is None:
                qs = qs.none()
            else:
                qs = qs.filter(Q(
                    star__location__inradius=(
                        (self.coords.ra.to_value(), self.coords.dec.to_value()),
                        self.search_radius
                    )
                ))

        sort_fields = (
            'distance',
            'star__superwasp_id',
            'period_length',
            'classification',
            'star___mean_magnitude',
            'star___max_magnitude',
            'star___min_magnitude'
        )
        self.sort = params.get('sort', None)
        if self.sort not in sort_fields:
            self.sort = sort_fields[0]

        self.order = params.get('order', None)
        if self.order == 'desc':
            order_prefix = '-'
        else:
            order_prefix = ''
            self.order = 'asc' # To ditch any invalid values
        
        if self.coords is None:
            self.coords = SkyCoord(0,0, unit=u.deg)

        qs = qs.annotate(
            distance=Distance('star__location', (
                self.coords.ra.to_value(), self.coords.dec.to_value(),
            )),
        ).order_by('{}{}'.format(order_prefix, self.sort))

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['min_period'] = self.min_period
        context['max_period'] = self.max_period
        context['min_magnitude'] = self.min_magnitude
        context['max_magnitude'] = self.max_magnitude
        context['certain_period'] = self.certain_period
        context['uncertain_period'] = self.uncertain_period
        context['type_pulsator'] = self.type_pulsator
        context['type_eaeb'] = self.type_eaeb
        context['type_ew'] = self.type_ew
        context['type_rotator'] = self.type_rotator
        context['type_unknown'] = self.type_unknown
        context['search'] = self.search
        context['search_radius'] = self.search_radius
        context['coords'] = self.coords
        context['sort'] = self.sort
        context['order'] = self.order

        return context


class IndexListView(StarListView):
    template_name = 'starcatalogue/index.html'


class DownloadView(TemplateView):
    template_name = 'starcatalogue/download.html'


class GenerateExportView(View):
    def get(self, request):
        return HttpResponseRedirect(reverse('vespa'))

    def post(self, request):
        try:
            min_period = request.POST.get('min_period', None)
            if not min_period:
                min_period = None

            max_period = request.POST.get('max_period', None)
            if not max_period:
                max_period = None

            min_magnitude = request.POST.get('min_magnitude', None)
            if not min_magnitude:
                min_magnitude = None

            max_magnitude = request.POST.get('max_magnitude', None)
            if not max_magnitude:
                max_magnitude = None

            search_radius = request.POST.get('search_radius', None)
            if not search_radius:
                search_radius = None

            export, created = DataExport.objects.get_or_create(
                data_version=settings.DATA_VERSION,
                min_period = min_period,
                max_period = max_period,
                min_magnitude = min_magnitude,
                max_magnitude = max_magnitude,
                certain_period = DataExport.CHECKBOX_CHOICES_DICT[request.POST.get('certain_period', 'on')],
                uncertain_period = DataExport.CHECKBOX_CHOICES_DICT[request.POST.get('uncertain_period', 'on')],
                type_pulsator = DataExport.CHECKBOX_CHOICES_DICT[request.POST.get('type_pulsator', 'on')],
                type_eaeb = DataExport.CHECKBOX_CHOICES_DICT[request.POST.get('type_eaeb', 'on')],
                type_ew = DataExport.CHECKBOX_CHOICES_DICT[request.POST.get('type_ew', 'on')],
                type_rotator = DataExport.CHECKBOX_CHOICES_DICT[request.POST.get('type_rotator', 'on')],
                type_unknown = DataExport.CHECKBOX_CHOICES_DICT[request.POST.get('type_unknown', 'on')],
                search = request.POST.get('search', None),
                search_radius = search_radius,
            )
            if (
                export.export_status in (export.STATUS_PENDING, export.STATUS_FAILED) 
                or (export.export_status == export.STATUS_RUNNING and AsyncResult(export.celery_task_id).ready())
            ):
                export.celery_task_id = generate_export.delay(export.id).id
                export.save()
            return HttpResponseRedirect(reverse('view_export', kwargs={'pk': export.id.hex}))
        except (ValueError, TypeError):
            return HttpResponseBadRequest('Bad Request')


class DataExportView(DetailView):
    model = DataExport


class SourceView(DetailView):
    model = Star

    def get_object(self, queryset=None):
        return get_object_or_404(self.model, superwasp_id=self.kwargs['swasp_id'])


from .tasks import generate_export