from decimal import Decimal

from .models import Grading, Result


FIRST_CLASS_GPA = Decimal('4.4')


def get_grade_for_marks(marks):
    grading_scale = Grading.objects.order_by('min_marks')
    return next(
        (
            grade
            for grade in grading_scale
            if grade.min_marks <= marks <= grade.max_marks
        ),
        None,
    )


def _calculate_weighted_average(results):
    results = list(
        results.select_related(
            'student',
            'unit',
            'unit__credit_allocation',
        )
    )
    if not results:
        return None

    grading_scale = list(Grading.objects.order_by('min_marks'))
    weighted_points = Decimal('0')
    total_credits = 0

    for result in results:
        credit_allocation = getattr(result.unit, 'credit_allocation', None)
        if (
            result.unit.course_id is None
            or result.student.course_id != result.unit.course_id
            or credit_allocation is None
        ):
            return None

        credit_units = credit_allocation.credit_units
        if credit_units <= 0:
            return None

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

        weighted_points += grade.grade_points * credit_units
        total_credits += credit_units

    if total_credits <= 0:
        return None

    return round(weighted_points / Decimal(total_credits), 2)


def calculate_gpa(student, session):
    results = Result.objects.filter(student=student, session=session)
    return _calculate_weighted_average(results)


def calculate_cgpa(student):
    results = Result.objects.filter(student=student)
    return _calculate_weighted_average(results)


def is_first_class(cgpa):
    return cgpa is not None and cgpa >= FIRST_CLASS_GPA
