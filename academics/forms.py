from django import forms

from .models import (
    Course,
    CourseUnit,
    CreditUnitAllocation,
    Faculty,
    Lecturer,
    Result,
    Student,
    StudySession,
    UnitAssignment,
)


class CourseByFacultySelect(forms.Select):
    def __init__(self, courses, *args, **kwargs):
        self.course_faculties = {
            str(course.pk): str(course.faculty_id)
            for course in courses
        }
        super().__init__(*args, **kwargs)

    def create_option(
        self,
        name,
        value,
        label,
        selected,
        index,
        subindex=None,
        attrs=None,
    ):
        option = super().create_option(
            name,
            value,
            label,
            selected,
            index,
            subindex=subindex,
            attrs=attrs,
        )
        faculty_id = self.course_faculties.get(str(value))
        if faculty_id:
            option['attrs']['data-faculty-id'] = faculty_id
        return option


class StudentForm(forms.ModelForm):
    faculty = forms.ModelChoiceField(
        queryset=Faculty.objects.order_by('faculty_name'),
    )
    course = forms.ModelChoiceField(queryset=Course.objects.none())

    class Meta:
        model = Student
        fields = '__all__'
        widgets = {
            'date_of_birth': forms.DateInput(
                attrs={'type': 'date'},
                format='%Y-%m-%d',
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        courses = list(
            Course.objects.select_related('faculty').order_by('course_name')
        )
        self.fields['course'].queryset = Course.objects.filter(
            pk__in=[course.pk for course in courses]
        )
        self.fields['course'].widget = CourseByFacultySelect(
            courses,
            choices=self.fields['course'].choices,
        )
        if self.instance.pk:
            self.initial['faculty'] = self.instance.faculty_id

        if self.is_bound:
            faculty_id = self.data.get(self.add_prefix('faculty'))
            if faculty_id:
                try:
                    faculty_id = int(faculty_id)
                except (TypeError, ValueError):
                    self.fields['course'].queryset = Course.objects.none()
                else:
                    self.fields['course'].queryset = self.fields[
                        'course'
                    ].queryset.filter(faculty_id=faculty_id)
            else:
                self.fields['course'].queryset = Course.objects.none()


class CourseForm(forms.ModelForm):
    duration = forms.TypedChoiceField(
        choices=Course.Duration.choices,
        coerce=int,
        required=True,
        label='Duration (years)',
    )

    class Meta:
        model = Course
        fields = '__all__'


class LecturerForm(forms.ModelForm):
    class Meta:
        model = Lecturer
        exclude = ('user',)


class CourseUnitForm(forms.ModelForm):
    class Meta:
        model = CourseUnit
        exclude = ('lecturers',)


class CreditUnitAllocationForm(forms.ModelForm):
    credit_units = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={'min': 1}),
        label='Credit units',
        help_text='Enter the credit value assigned to this course unit.',
    )

    class Meta:
        model = CreditUnitAllocation
        fields = ('unit', 'credit_units')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['unit'].queryset = CourseUnit.objects.select_related(
            'course'
        ).filter(course__isnull=False).order_by(
            'course__course_name',
            'unit_name',
        )
        self.fields['unit'].label = 'Course unit'


class UnitAssignmentForm(forms.ModelForm):
    class Meta:
        model = UnitAssignment
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['unit'].queryset = CourseUnit.objects.select_related(
            'course'
        ).order_by('unit_name')
        self.fields['unit'].label = 'Course unit'
        self.fields['lecturer'].label = 'Lecturer'

    def clean(self):
        cleaned_data = super().clean()
        lecturer = cleaned_data.get('lecturer')
        unit = cleaned_data.get('unit')
        if lecturer and unit:
            if unit.course_id is None:
                self.add_error(
                    'unit',
                    'Assign this unit to a course before assigning it to a lecturer.',
                )
            elif lecturer.faculty_id != unit.course.faculty_id:
                self.add_error(
                    'unit',
                    "The unit must belong to the lecturer's faculty.",
                )
        return cleaned_data


class ResultEntryForm(forms.ModelForm):
    class Meta:
        model = Result
        fields = ('student', 'unit', 'session', 'marks')
        widgets = {
            'marks': forms.NumberInput(attrs={'min': 0, 'max': 100}),
        }

    def __init__(self, *args, lecturer, **kwargs):
        super().__init__(*args, **kwargs)
        self.lecturer = lecturer
        self.fields['unit'].label = 'Course unit'
        self.fields['unit'].queryset = lecturer.course_units.filter(
            course__isnull=False,
            credit_allocation__credit_units__gt=0,
        ).order_by('unit_name')
        self.fields['unit'].help_text = (
            'Choose a course unit assigned to you.'
        )
        self.fields['session'].queryset = StudySession.objects.filter(
            status=StudySession.Status.ONGOING
        ).order_by('-academic_year', 'semester')
        self.fields['marks'].help_text = 'Enter a whole-number mark from 0 to 100.'

    def save(self, commit=True):
        result = super().save(commit=False)
        result.entered_by = self.lecturer
        if commit:
            result.save()
            self.save_m2m()
        return result
