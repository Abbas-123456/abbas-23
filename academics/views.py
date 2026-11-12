from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models.deletion import ProtectedError
from django import forms
from django.db import models as django_models
from django.forms import modelform_factory
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from . import models
from .access import (
    ROLE_COORDINATOR,
    ROLE_LECTURER,
    ROLE_REGISTRAR,
    coordinator_required,
    has_role,
    lecturer_required,
    registrar_required,
)
from .forms import (
    CourseForm,
    CourseUnitForm,
    CreditUnitAllocationForm,
    LecturerForm,
    ResultEntryForm,
    StudentForm,
    UnitAssignmentForm,
)
from .services import (
    calculate_cgpa,
    calculate_semester_gpa,
    get_grade_for_marks,
    is_first_class,
)


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
    'unit-assignments': models.CreditUnitAllocation,
    'lecturer-assignments': models.UnitAssignment,
}


def get_model(model_name):
    try:
        return MODEL_REGISTRY[model_name]
    except KeyError as exc:
        raise Http404('Academic record type not found.') from exc


def get_display_fields(model):
    if model is models.CreditUnitAllocation:
        return [
            ('Course', 'unit.course'),
            ('Course unit', 'unit'),
            ('Credit units', 'credit_units'),
        ]
    if model is models.UnitAssignment:
        return [
            ('Lecturer', 'lecturer'),
            ('Faculty', 'lecturer.faculty'),
            ('Course', 'unit.course'),
            ('Course unit', 'unit'),
        ]
    if model is models.Lecturer:
        return [
            ('Lecturer name', 'lecturer_name'),
            ('Faculty', 'faculty'),
            ('Department', 'department'),
            ('Courses taught', 'courses_taught'),
            ('Contact', 'contact'),
        ]
    if model is models.CourseUnit:
        return [
            ('Course unit', 'unit_name'),
            ('Course', 'course'),
            ('Faculty', 'course.faculty'),
            ('Academic year', 'academic_year'),
            ('Semester', 'semester'),
        ]
    return [
        (
            'Course unit' if field.name == 'unit' else field.verbose_name.title(),
            field.name,
        )
        for field in model._meta.concrete_fields
    ]


def get_display_values(obj, fields):
    return [
        (label, _get_display_value(obj, name))
        for label, name in fields
    ]


def _get_display_value(obj, field_path):
    value = obj
    for field_name in field_path.split('.'):
        value = getattr(value, field_name, None)
        if value is None:
            return 'Not assigned'
    return str(value)


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
    if has_role(request.user, ROLE_REGISTRAR):
        result_count = models.Result.objects.count()
        grade_summary = []
        for grade in models.Grading.objects.order_by('-min_marks'):
            grade_count = models.Result.objects.filter(
                marks__gte=grade.min_marks,
                marks__lte=grade.max_marks,
            ).count()
            grade_summary.append(
                {
                    'symbol': grade.grade_symbol,
                    'count': grade_count,
                    'percent': round(grade_count * 100 / result_count)
                    if result_count
                    else 0,
                    'min_marks': grade.min_marks,
                    'max_marks': grade.max_marks,
                }
            )
        return render(
            request,
            'academics/dashboard.html',
            {
                'model_links': MODEL_REGISTRY.keys(),
                'student_count': models.Student.objects.count(),
                'lecturer_count': models.Lecturer.objects.count(),
                'course_count': models.Course.objects.count(),
                'faculty_count': models.Faculty.objects.count(),
                'course_unit_count': models.CourseUnit.objects.count(),
                'unit_assignment_count': models.CreditUnitAllocation.objects.count(),
                'lecturer_assignment_count': models.UnitAssignment.objects.count(),
                'ongoing_session_count': models.StudySession.objects.filter(
                    status=models.StudySession.Status.ONGOING
                ).count(),
                'result_count': result_count,
                'grade_summary': grade_summary,
                'recent_results': models.Result.objects.select_related(
                    'student',
                    'unit',
                    'session',
                ).order_by('-pk')[:6],
            },
        )
    if has_role(request.user, ROLE_LECTURER):
        return redirect('academics:lecturer-dashboard')
    if has_role(request.user, ROLE_COORDINATOR):
        return redirect('academics:coordinator-dashboard')
    raise PermissionDenied


def can_view_model(user, model_name):
    if model_name == 'timetables':
        return has_role(user, ROLE_REGISTRAR) or has_role(
            user,
            ROLE_COORDINATOR,
        )
    return has_role(user, ROLE_REGISTRAR)


def can_manage_model(user, model_name):
    if model_name == 'timetables':
        return has_role(user, ROLE_COORDINATOR)
    return has_role(user, ROLE_REGISTRAR)


@login_required
def model_list(request, model_name):
    if not can_view_model(request.user, model_name):
        raise PermissionDenied

    model = get_model(model_name)
    fields = get_display_fields(model)
    queryset = model.objects.all()
    if model is models.Lecturer:
        queryset = queryset.select_related('faculty').prefetch_related(
            'unit_assignments__unit__course'
        )
    elif model is models.CourseUnit:
        queryset = queryset.select_related('course__faculty')
    elif model is models.CreditUnitAllocation:
        queryset = queryset.select_related('unit__course')
    elif model is models.UnitAssignment:
        queryset = queryset.select_related(
            'lecturer__faculty',
            'unit__course',
        )
    records = [
        (obj, get_display_values(obj, fields))
        for obj in queryset
    ]
    return render(
        request,
        'academics/model_list.html',
        {
            'model_name': model_name,
            'model_label': model._meta.verbose_name_plural.title(),
            'fields': [label for label, _ in fields],
            'records': records,
            'read_only': not can_manage_model(request.user, model_name),
        },
    )


@login_required
def model_detail(request, model_name, pk):
    if not can_view_model(request.user, model_name):
        raise PermissionDenied

    model = get_model(model_name)
    obj = get_object_or_404(model, pk=pk)
    if model is models.Lecturer:
        obj = (
            model.objects.select_related('faculty')
            .prefetch_related('unit_assignments__unit__course')
            .get(pk=pk)
        )
    elif model is models.CourseUnit:
        obj = model.objects.select_related('course__faculty').get(pk=pk)
    elif model is models.CreditUnitAllocation:
        obj = model.objects.select_related('unit__course').get(pk=pk)
    elif model is models.UnitAssignment:
        obj = model.objects.select_related(
            'lecturer__faculty',
            'unit__course',
        ).get(pk=pk)
    return render(
        request,
        'academics/model_detail.html',
        {
            'model_name': model_name,
            'model_label': model._meta.verbose_name.title(),
            'object': obj,
            'fields': get_display_values(obj, get_display_fields(model)),
            'read_only': not can_manage_model(request.user, model_name),
        },
    )


@login_required
def model_form(request, model_name, pk=None):
    if not can_manage_model(request.user, model_name):
        raise PermissionDenied

    model = get_model(model_name)
    obj = get_object_or_404(model, pk=pk) if pk is not None else None
    form_classes = {
        models.Course: CourseForm,
        models.Student: StudentForm,
        models.Lecturer: LecturerForm,
        models.CourseUnit: CourseUnitForm,
        models.CreditUnitAllocation: CreditUnitAllocationForm,
        models.UnitAssignment: UnitAssignmentForm,
    }
    form_class = form_classes.get(model)
    if form_class is None:
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
    if not can_manage_model(request.user, model_name):
        raise PermissionDenied

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


@lecturer_required
def lecturer_dashboard(request):
    lecturer = get_object_or_404(models.Lecturer, user=request.user)
    units = lecturer.course_units.select_related(
        'course',
        'credit_allocation',
    ).order_by('unit_name')
    results = list(
        models.Result.objects.filter(unit__in=units)
        .select_related(
            'student',
            'unit',
            'unit__credit_allocation',
            'session',
        )
        .order_by('-session__academic_year', 'student__student_name')
    )
    grades_by_marks = {}
    result_rows = []
    for result in results:
        if result.marks not in grades_by_marks:
            grades_by_marks[result.marks] = get_grade_for_marks(result.marks)
        result_rows.append(
            {
                'result': result,
                'grade': grades_by_marks[result.marks],
            }
        )
    return render(
        request,
        'academics/lecturer_dashboard.html',
        {
            'lecturer': lecturer,
            'units': units,
            'result_rows': result_rows,
        },
    )


@lecturer_required
def result_entry(request):
    lecturer = get_object_or_404(models.Lecturer, user=request.user)
    form = ResultEntryForm(
        request.POST or None,
        lecturer=lecturer,
    )
    if request.method == 'POST' and form.is_valid():
        result = form.save()
        grade = get_grade_for_marks(result.marks)
        semester_gpa = calculate_semester_gpa(result.student, result.session)
        cgpa = calculate_cgpa(result.student)
        return render(
            request,
            'academics/result_entry_success.html',
            {
                'result': result,
                'grade': grade,
                'semester_gpa': semester_gpa,
                'cgpa': cgpa,
                'first_class': is_first_class(cgpa),
            },
        )

    return render(
        request,
        'academics/result_entry_form.html',
        {'form': form},
    )


@coordinator_required
def coordinator_dashboard(request):
    results = (
        models.Result.objects.select_related(
            'student',
            'unit',
            'unit__credit_allocation',
            'session',
        )
        .order_by(
            '-session__academic_year',
            'session__semester',
            'student__student_name',
        )
    )
    result_rows = []
    student_cgpas = {}
    student_semester_gpas = {}
    grades_by_marks = {}
    for result in results:
        if result.student_id not in student_cgpas:
            student_cgpas[result.student_id] = calculate_cgpa(result.student)
        semester_key = (result.student_id, result.session_id)
        if semester_key not in student_semester_gpas:
            student_semester_gpas[semester_key] = calculate_semester_gpa(
                result.student,
                result.session,
            )
        if result.marks not in grades_by_marks:
            grades_by_marks[result.marks] = get_grade_for_marks(result.marks)
        cgpa = student_cgpas[result.student_id]
        result_rows.append(
            {
                'result': result,
                'grade': grades_by_marks[result.marks],
                'semester_gpa': student_semester_gpas[semester_key],
                'cgpa': cgpa,
                'first_class': is_first_class(cgpa),
            }
        )

    return render(
        request,
        'academics/coordinator_dashboard.html',
        {'result_rows': result_rows},
    )
