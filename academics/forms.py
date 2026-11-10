from django import forms

from .models import Result, StudySession


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
        self.fields['unit'].queryset = lecturer.course_units.order_by('unit_name')
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
