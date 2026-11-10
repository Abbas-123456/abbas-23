from django.contrib import admin

from .models import (
    Course,
    CourseUnit,
    Faculty,
    Grading,
    Lecturer,
    Result,
    Student,
    StudySession,
    Timetable,
    UnitAssignment,
)


@admin.register(Lecturer)
class LecturerAdmin(admin.ModelAdmin):
    list_display = ('lecturer_name', 'user', 'department')
    search_fields = ('lecturer_name', 'department', 'user__username')


@admin.register(CourseUnit)
class CourseUnitAdmin(admin.ModelAdmin):
    list_display = ('unit_name', 'academic_year', 'semester', 'credit_units')
    search_fields = ('unit_name', 'academic_year')


@admin.register(UnitAssignment)
class UnitAssignmentAdmin(admin.ModelAdmin):
    list_display = ('lecturer', 'unit')
    list_filter = ('unit__academic_year', 'unit__semester')


admin.site.register(
    (Course, Faculty, Grading, Result, Student, StudySession, Timetable)
)
