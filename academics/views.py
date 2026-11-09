from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models.deletion import ProtectedError
from django import forms
from django.db import models as django_models
from django.forms import modelform_factory
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from . import models


MODEL_REGISTRY = {
    'faculties': models.Faculty,
    'courses': models.Course,
    'students': models.Student,
    'lecturers': models.Lecturer,
    'course-units': models.CourseUnit,
    'timetables': models.Timetable,
    'study-sessions': models.StudySession,
    'gradings': models.Grading,
    'results': models.Result,
}


def get_model(model_name):
    try:
        return MODEL_REGISTRY[model_name]
    except KeyError as exc:
        raise Http404('Academic record type not found.') from exc


def get_display_fields(model):
    return [
        (field.verbose_name.title(), field.name)
        for field in model._meta.concrete_fields
    ]


def get_display_values(obj, fields):
    return [
        (label, str(getattr(obj, name)))
        for label, name in fields
    ]


def get_form_widgets(model):
    return {
        field.name: forms.DateInput(
            attrs={'type': 'date'},
            format='%Y-%m-%d',
        )
        for field in model._meta.fields
        if isinstance(field, django_models.DateField)
    }


@login_required
def index(request):
    return render(
        request,
        'academics/index.html',
        {'model_links': MODEL_REGISTRY.keys()},
    )


@login_required
def model_list(request, model_name):
    model = get_model(model_name)
    fields = get_display_fields(model)
    records = [
        (obj, get_display_values(obj, fields))
        for obj in model.objects.all()
    ]
    return render(
        request,
        'academics/model_list.html',
        {
            'model_name': model_name,
            'model_label': model._meta.verbose_name_plural.title(),
            'fields': [label for label, _ in fields],
            'records': records,
        },
    )


@login_required
def model_detail(request, model_name, pk):
    model = get_model(model_name)
    obj = get_object_or_404(model, pk=pk)
    return render(
        request,
        'academics/model_detail.html',
        {
            'model_name': model_name,
            'model_label': model._meta.verbose_name.title(),
            'object': obj,
            'fields': get_display_values(obj, get_display_fields(model)),
        },
    )


@login_required
def model_form(request, model_name, pk=None):
    model = get_model(model_name)
    obj = get_object_or_404(model, pk=pk) if pk is not None else None
    form_class = modelform_factory(
        model,
        fields='__all__',
        widgets=get_form_widgets(model),
    )
    form = form_class(request.POST or None, instance=obj)

    if request.method == 'POST' and form.is_valid():
        saved_obj = form.save()
        return redirect(
            reverse(
                'academics:model-detail',
                kwargs={'model_name': model_name, 'pk': saved_obj.pk},
            )
        )

    return render(
        request,
        'academics/model_form.html',
        {
            'model_name': model_name,
            'model_label': model._meta.verbose_name.title(),
            'form': form,
            'object': obj,
        },
    )


@login_required
def model_delete(request, model_name, pk):
    model = get_model(model_name)
    obj = get_object_or_404(model, pk=pk)
    if request.method == 'POST':
        try:
            obj.delete()
        except ProtectedError:
            messages.error(
                request,
                'This record cannot be deleted because other records depend on it.',
            )
            return redirect(
                'academics:model-detail',
                model_name=model_name,
                pk=obj.pk,
            )
        return redirect('academics:model-list', model_name=model_name)
    return render(
        request,
        'academics/model_confirm_delete.html',
        {
            'model_name': model_name,
            'model_label': model._meta.verbose_name.title(),
            'object': obj,
        },
    )
