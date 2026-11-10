from .models import Grading, Result


FIRST_CLASS_GPA = 4.4


def calculate_weighted_gpa(student):
    results = Result.objects.filter(student=student).select_related('unit')
    if not results.exists():
        return None

    grading_scale = list(Grading.objects.order_by('min_marks'))
    weighted_points = 0
    total_credits = 0

    for result in results:
        grade = next(
            (
                item
                for item in grading_scale
                if item.min_marks <= result.marks <= item.max_marks
            ),
            None,
        )
        if grade is None:
            return None

        weighted_points += grade.grade_points * result.unit.credit_units
        total_credits += result.unit.credit_units

    if total_credits == 0:
        return None

    return round(weighted_points / total_credits, 2)


def is_first_class(weighted_gpa):
    return weighted_gpa is not None and weighted_gpa >= FIRST_CLASS_GPA
