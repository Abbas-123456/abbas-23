from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from .access import ROLE_COORDINATOR, ROLE_LECTURER, ROLE_REGISTRAR
from .forms import ResultEntryForm
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
from .services import (
    calculate_cgpa,
    calculate_gpa,
    get_grade_for_marks,
    is_first_class,
)
from .views import MODEL_REGISTRY


class AcademicCrudViewTests(TestCase):
    def setUp(self):
        registrar_group, _ = Group.objects.get_or_create(name=ROLE_REGISTRAR)
        self.user = get_user_model().objects.create_user(
            username='staff',
            password='test-password-123',
        )
        self.user.groups.add(registrar_group)
        self.client.force_login(self.user)

    def test_all_model_lists_and_create_forms_are_accessible(self):
        for model_name in MODEL_REGISTRY:
            with self.subTest(model_name=model_name):
                for url_name in ('model-list', 'model-create'):
                    response = self.client.get(
                        reverse(f'academics:{url_name}', args=[model_name])
                    )
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, '/static/academics/css/app.css')
                    self.assertContains(response, 'bootstrap-icons')

    def test_date_fields_render_as_calendar_inputs(self):
        test_cases = (
            ('students', 'date_of_birth'),
            ('timetables', 'day'),
        )
        for model_name, field_name in test_cases:
            with self.subTest(model_name=model_name):
                response = self.client.get(
                    reverse('academics:model-create', args=[model_name])
                )
                field = response.context['form'][field_name]
                self.assertEqual(field.field.widget.input_type, 'date')
                self.assertEqual(field.field.widget.format, '%Y-%m-%d')

    def test_student_form_shows_faculty_and_course_choices(self):
        faculty = Faculty.objects.create(
            faculty_id=1,
            faculty_name='Engineering',
        )
        Course.objects.create(
            course_code='CSC101',
            course_name='Computer Science',
            duration=Course.Duration.THREE_YEARS,
            faculty=faculty,
        )
        response = self.client.get(
            reverse('academics:model-create', args=['students'])
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('faculty', response.context['form'].fields)
        self.assertIn('course', response.context['form'].fields)
        self.assertContains(response, 'data-faculty-id="1"')
        self.assertContains(response, 'id="id_faculty"')

    def test_student_faculty_must_match_selected_course(self):
        engineering = Faculty.objects.create(
            faculty_id=1,
            faculty_name='Engineering',
        )
        law = Faculty.objects.create(faculty_id=2, faculty_name='Law')
        course = Course.objects.create(
            course_code='CSC101',
            course_name='Computer Science',
            duration=Course.Duration.THREE_YEARS,
            faculty=engineering,
        )
        other_course = Course.objects.create(
            course_code='LAW101',
            course_name='Law',
            duration=Course.Duration.FOUR_YEARS,
            faculty=law,
        )
        payload = {
            'reg_no': 'REG001',
            'student_name': 'Amina Student',
            'gender': Student.Gender.FEMALE,
            'contact': '0700000000',
            'faculty': engineering.pk,
            'course': course.pk,
        }
        response = self.client.post(
            reverse('academics:model-create', args=['students']),
            payload,
        )

        student = Student.objects.get(reg_no='REG001')
        self.assertRedirects(
            response,
            reverse('academics:model-detail', args=['students', student.pk]),
        )
        self.assertEqual(student.faculty, engineering)

        payload.update(reg_no='REG002', faculty=engineering.pk, course=other_course.pk)
        response = self.client.post(
            reverse('academics:model-create', args=['students']),
            payload,
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Student.objects.filter(reg_no='REG002').exists())
        self.assertFormError(
            response.context['form'],
            'course',
            'Select a valid choice. That choice is not one of the available choices.',
        )

        payload.update(reg_no='REG003', faculty='invalid', course=course.pk)
        response = self.client.post(
            reverse('academics:model-create', args=['students']),
            payload,
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Student.objects.filter(reg_no='REG003').exists())
        self.assertIn('faculty', response.context['form'].errors)

    def test_registrar_can_assign_course_units_and_study_period(self):
        faculty = Faculty.objects.create(
            faculty_id=1,
            faculty_name='Engineering',
        )
        course = Course.objects.create(
            course_code='CSC101',
            course_name='Computer Science',
            duration=Course.Duration.THREE_YEARS,
            faculty=faculty,
        )

        response = self.client.post(
            reverse('academics:model-create', args=['course-units']),
            {
                'unit_name': 'Algorithms',
                'academic_year': '2026/2027',
                'semester': CourseUnit.Semester.ONE,
                'course': course.pk,
            },
        )
        unit = CourseUnit.objects.get(unit_name='Algorithms')
        self.assertRedirects(
            response,
            reverse('academics:model-detail', args=['course-units', unit.pk]),
        )
        self.assertEqual(unit.course, course)
        course_unit_form_response = self.client.get(
            reverse('academics:model-create', args=['course-units'])
        )
        self.assertNotIn(
            'credit_units',
            course_unit_form_response.context['form'].fields,
        )

        response = self.client.post(
            reverse('academics:model-create', args=['unit-assignments']),
            {'unit': unit.pk, 'credit_units': 7},
        )
        allocation = CreditUnitAllocation.objects.get(unit=unit)
        self.assertRedirects(
            response,
            reverse(
                'academics:model-detail',
                args=['unit-assignments', allocation.pk],
            ),
        )
        self.assertEqual(allocation.credit_units, 7)
        allocation_response = self.client.get(
            reverse('academics:model-create', args=['unit-assignments'])
        )
        self.assertNotIn('lecturer', allocation_response.context['form'].fields)
        self.assertIn('credit_units', allocation_response.context['form'].fields)

    def test_credit_allocation_requires_positive_credit_units(self):
        unit = CourseUnit.objects.create(
            unit_name='Algorithms',
            academic_year='2026/2027',
            semester=CourseUnit.Semester.ONE,
        )

        response = self.client.post(
            reverse('academics:model-create', args=['unit-assignments']),
            {'unit': unit.pk, 'credit_units': 0},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(CreditUnitAllocation.objects.filter(unit=unit).exists())
        self.assertIn('credit_units', response.context['form'].errors)

        response = self.client.post(
            reverse('academics:model-create', args=['study-sessions']),
            {
                'academic_year': '2026/2027',
                'semester': StudySession.Semester.ONE,
                'study_period': StudySession.Period.EVENING,
                'status': StudySession.Status.ONGOING,
            },
        )
        session = StudySession.objects.get(academic_year='2026/2027')
        self.assertRedirects(
            response,
            reverse('academics:model-detail', args=['study-sessions', session.pk]),
        )
        self.assertEqual(session.study_period, StudySession.Period.EVENING)

    def test_registrar_can_assign_lecturers_to_a_faculty(self):
        faculty = Faculty.objects.create(
            faculty_id=1,
            faculty_name='Engineering',
        )
        response = self.client.post(
            reverse('academics:model-create', args=['lecturers']),
            {
                'lecturer_name': 'Grace Lecturer',
                'gender': Lecturer.Gender.FEMALE,
                'contact': '0700000000',
                'department': 'Computer Science',
                'faculty': faculty.pk,
                'user': '',
            },
        )

        lecturer = Lecturer.objects.get(lecturer_name='Grace Lecturer')
        self.assertRedirects(
            response,
            reverse('academics:model-detail', args=['lecturers', lecturer.pk]),
        )
        self.assertEqual(lecturer.faculty, faculty)

    def test_lecturer_cannot_be_assigned_a_unit_from_another_faculty(self):
        engineering = Faculty.objects.create(
            faculty_id=1,
            faculty_name='Engineering',
        )
        law = Faculty.objects.create(faculty_id=2, faculty_name='Law')
        law_course = Course.objects.create(
            course_code='LAW101',
            course_name='Law',
            duration=Course.Duration.THREE_YEARS,
            faculty=law,
        )
        law_unit = CourseUnit.objects.create(
            unit_name='Legal Systems',
            academic_year='2026/2027',
            semester=CourseUnit.Semester.ONE,
            course=law_course,
        )
        lecturer = Lecturer.objects.create(
            lecturer_name='Grace Lecturer',
            gender=Lecturer.Gender.FEMALE,
            contact='0700000000',
            department='Computer Science',
            faculty=engineering,
        )

        response = self.client.post(
            reverse('academics:model-create', args=['lecturer-assignments']),
            {'lecturer': lecturer.pk, 'unit': law_unit.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            UnitAssignment.objects.filter(lecturer=lecturer, unit=law_unit).exists()
        )
        self.assertIn('unit', response.context['form'].errors)

    def test_dashboard_uses_static_styles_and_live_academic_counts(self):
        response = self.client.get(reverse('academics:index'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '/static/academics/css/app.css')
        self.assertContains(response, '/static/academics/css/dashboard.css')
        self.assertContains(response, 'bootstrap-icons')
        self.assertContains(response, 'Results entered')
        self.assertContains(response, 'Grade distribution')
        self.assertContains(response, 'Credit unit allocations')
        self.assertContains(response, 'Lecturer assignments')
        self.assertEqual(response.context['student_count'], 0)
        self.assertEqual(response.context['result_count'], 0)
        self.assertTrue(finders.find('academics/css/app.css'))
        self.assertTrue(finders.find('academics/css/dashboard.css'))

    def test_faculty_create_update_and_delete(self):
        faculty_list = reverse('academics:model-list', args=['faculties'])
        create_url = reverse('academics:model-create', args=['faculties'])

        response = self.client.post(
            create_url,
            {'faculty_id': 1, 'faculty_name': 'Science'},
        )
        faculty = Faculty.objects.get(pk=1)
        detail_url = reverse(
            'academics:model-detail',
            args=['faculties', faculty.pk],
        )
        self.assertEqual(self.client.get(detail_url).status_code, 200)
        self.assertEqual(
            self.client.get(
                reverse('academics:model-delete', args=['faculties', faculty.pk])
            ).status_code,
            200,
        )
        self.assertRedirects(
            response,
            detail_url,
        )

        response = self.client.post(
            reverse('academics:model-update', args=['faculties', faculty.pk]),
            {'faculty_id': 1, 'faculty_name': 'Faculty of Science'},
        )
        self.assertRedirects(
            response,
            reverse('academics:model-detail', args=['faculties', faculty.pk]),
        )
        faculty.refresh_from_db()
        self.assertEqual(faculty.faculty_name, 'Faculty of Science')

        response = self.client.post(
            reverse('academics:model-delete', args=['faculties', faculty.pk])
        )
        self.assertRedirects(response, faculty_list)
        self.assertFalse(Faculty.objects.filter(pk=faculty.pk).exists())

    def test_course_duration_is_a_required_three_to_five_year_choice(self):
        faculty = Faculty.objects.create(
            faculty_id=1,
            faculty_name='Engineering',
        )
        response = self.client.get(
            reverse('academics:model-create', args=['courses'])
        )
        duration_field = response.context['form'].fields['duration']

        self.assertEqual(duration_field.widget.input_type, 'select')
        self.assertTrue(duration_field.required)
        self.assertEqual(
            duration_field.choices,
            [
                (3, '3 years'),
                (4, '4 years'),
                (5, '5 years'),
            ],
        )

        response = self.client.post(
            reverse('academics:model-create', args=['courses']),
            {
                'course_code': 'CSC101',
                'course_name': 'Computer Science',
                'duration': '4',
                'faculty': faculty.pk,
            },
        )

        course = Course.objects.get(course_code='CSC101')
        self.assertRedirects(
            response,
            reverse('academics:model-detail', args=['courses', course.pk]),
        )
        self.assertEqual(course.duration, Course.Duration.FOUR_YEARS)

        response = self.client.post(
            reverse('academics:model-create', args=['courses']),
            {
                'course_code': 'LAW101',
                'course_name': 'Law',
                'duration': '6',
                'faculty': faculty.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Course.objects.filter(course_code='LAW101').exists())
        self.assertIn('duration', response.context['form'].errors)

    def test_deleting_referenced_faculty_shows_message(self):
        faculty = Faculty.objects.create(faculty_id=1, faculty_name='Science')
        Course.objects.create(
            course_code='CSC101',
            course_name='Computer Science',
            duration=Course.Duration.THREE_YEARS,
            faculty=faculty,
        )

        response = self.client.post(
            reverse('academics:model-delete', args=['faculties', faculty.pk]),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Faculty.objects.filter(pk=faculty.pk).exists())
        self.assertContains(response, 'other records depend on it')


class AuthenticationViewTests(TestCase):
    def test_academics_pages_require_login(self):
        response = self.client.get(reverse('academics:index'))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('academics:index')}",
        )

    def test_login_page_authenticates_and_redirects(self):
        get_user_model().objects.create_user(
            username='staff',
            password='test-password-123',
        )

        response = self.client.post(
            reverse('login'),
            {'username': 'staff', 'password': 'test-password-123'},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('academics:index'))
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_logout_requires_post_and_logs_out(self):
        get_user_model().objects.create_user(
            username='staff',
            password='test-password-123',
        )
        self.client.login(username='staff', password='test-password-123')

        response = self.client.post(reverse('logout'))

        self.assertRedirects(response, reverse('login'))
        protected_response = self.client.get(reverse('academics:index'))
        self.assertRedirects(
            protected_response,
            f"{reverse('login')}?next={reverse('academics:index')}",
        )


class RoleWorkflowTests(TestCase):
    def setUp(self):
        self.faculty = Faculty.objects.create(
            faculty_id=1,
            faculty_name='Science',
        )
        self.course = Course.objects.create(
            course_code='CSC101',
            course_name='Computer Science',
            duration=Course.Duration.THREE_YEARS,
            faculty=self.faculty,
        )
        self.student = Student.objects.create(
            reg_no='REG001',
            student_name='Amina Student',
            gender=Student.Gender.FEMALE,
            contact='0700000000',
            course=self.course,
            faculty=self.faculty,
        )
        self.session = StudySession.objects.create(
            academic_year='2025/2026',
            semester=StudySession.Semester.ONE,
            status=StudySession.Status.ONGOING,
        )
        self.unit = CourseUnit.objects.create(
            unit_name='Programming',
            academic_year='2025/2026',
            semester=CourseUnit.Semester.ONE,
            course=self.course,
        )
        CreditUnitAllocation.objects.create(unit=self.unit, credit_units=4)
        self.other_unit = CourseUnit.objects.create(
            unit_name='Calculus',
            academic_year='2025/2026',
            semester=CourseUnit.Semester.ONE,
            course=self.course,
        )
        CreditUnitAllocation.objects.create(unit=self.other_unit, credit_units=6)
        self.user = get_user_model().objects.create_user(
            username='lecturer',
            password='test-password-123',
        )
        lecturer_group, _ = Group.objects.get_or_create(name=ROLE_LECTURER)
        self.user.groups.add(lecturer_group)
        self.lecturer = Lecturer.objects.create(
            user=self.user,
            lecturer_name='Dr Lecturer',
            gender=Lecturer.Gender.MALE,
            contact='0710000000',
            department='Computer Science',
            faculty=self.faculty,
        )
        UnitAssignment.objects.create(lecturer=self.lecturer, unit=self.unit)
        UnitAssignment.objects.create(lecturer=self.lecturer, unit=self.other_unit)
    def test_lecturer_can_only_enter_marks_for_assigned_units(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('academics:result-entry'),
            {
                'student': self.student.pk,
                'unit': self.unit.pk,
                'session': self.session.pk,
                'marks': 90,
            },
        )

        result = Result.objects.get(student=self.student, unit=self.unit)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(result.entered_by, self.lecturer)
        self.assertContains(response, 'First Class')
        self.assertContains(response, '4.4')
        self.assertContains(response, 'A (5.0 points)')
        self.assertContains(response, 'Session GPA:')
        self.assertContains(response, 'Cumulative GPA (CGPA):')

        response = self.client.post(
            reverse('academics:result-entry'),
            {
                'student': self.student.pk,
                'unit': 9999,
                'session': self.session.pk,
                'marks': 90,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Result.objects.count(), 1)

    def test_result_entry_requires_a_student_from_the_unit_course(self):
        other_course = Course.objects.create(
            course_code='CSC202',
            course_name='Information Systems',
            duration=Course.Duration.THREE_YEARS,
            faculty=self.faculty,
        )
        other_student = Student.objects.create(
            reg_no='REG002',
            student_name='Other Student',
            gender=Student.Gender.MALE,
            contact='0700000001',
            course=other_course,
            faculty=self.faculty,
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('academics:result-entry'),
            {
                'student': other_student.pk,
                'unit': self.unit.pk,
                'session': self.session.pk,
                'marks': 90,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Result.objects.count(), 0)
        self.assertIn('student', response.context['form'].errors)

    def test_lecturer_cannot_access_registrar_crud(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse('academics:model-list', args=['students'])
        )

        self.assertEqual(response.status_code, 403)

    def test_coordinator_can_review_but_cannot_edit_results(self):
        result = Result.objects.create(
            student=self.student,
            unit=self.unit,
            session=self.session,
            marks=80,
        )
        Result.objects.create(
            student=self.student,
            unit=self.other_unit,
            session=self.session,
            marks=80,
        )
        coordinator = get_user_model().objects.create_user(
            username='coordinator',
            password='test-password-123',
        )
        coordinator_group, _ = Group.objects.get_or_create(
            name=ROLE_COORDINATOR
        )
        coordinator.groups.add(coordinator_group)
        self.client.force_login(coordinator)

        response = self.client.get(reverse('academics:coordinator-dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'First Class')
        self.assertContains(response, 'CGPA')

        response = self.client.get(
            reverse('academics:model-update', args=['results', result.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_session_gpa_and_cgpa_use_credit_units_and_count_every_attempt(self):
        previous_session = StudySession.objects.create(
            academic_year='2024/2025',
            semester=StudySession.Semester.TWO,
            status=StudySession.Status.COMPLETED,
        )
        Result.objects.create(
            student=self.student,
            unit=self.other_unit,
            session=self.session,
            marks=80,
        )
        Result.objects.create(
            student=self.student,
            unit=self.unit,
            session=self.session,
            marks=70,
        )
        Result.objects.create(
            student=self.student,
            unit=self.unit,
            session=previous_session,
            marks=44,
        )

        gpa = calculate_gpa(self.student, self.session)
        cgpa = calculate_cgpa(self.student)

        self.assertEqual(gpa, Decimal('4.60'))
        self.assertEqual(cgpa, Decimal('3.29'))
        self.assertTrue(is_first_class(gpa))
        self.assertTrue(is_first_class(Decimal('4.40')))
        self.assertFalse(is_first_class(cgpa))
        self.assertFalse(is_first_class(4.39))
        self.assertFalse(is_first_class(None))

    def test_shared_grading_scale_includes_plus_grades_and_half_points(self):
        expected = (
            (100, 'A', 5.0),
            (80, 'A', 5.0),
            (79, 'B+', 4.5),
            (75, 'B+', 4.5),
            (74, 'B', 4.0),
            (70, 'B', 4.0),
            (69, 'C+', 3.5),
            (65, 'C+', 3.5),
            (64, 'C', 3.0),
            (60, 'C', 3.0),
            (59, 'D+', 2.5),
            (55, 'D+', 2.5),
            (54, 'D', 2.0),
            (50, 'D', 2.0),
            (49, 'E', 1.5),
            (45, 'E', 1.5),
            (44, 'F', 0.0),
            (0, 'F', 0.0),
        )

        for marks, symbol, points in expected:
            with self.subTest(marks=marks):
                grade = get_grade_for_marks(marks)
                self.assertIsNotNone(grade)
                self.assertEqual(grade.grade_symbol, symbol)
                self.assertEqual(grade.grade_points, Decimal(str(points)))

    def test_session_gpa_is_unavailable_without_results(self):
        self.assertIsNone(calculate_gpa(self.student, self.session))
        self.assertIsNone(calculate_cgpa(self.student))

    def test_unassigned_course_units_are_not_used_for_results_or_gpa(self):
        unassigned_unit = CourseUnit.objects.create(
            unit_name='Unassigned unit',
            academic_year='2025/2026',
            semester=CourseUnit.Semester.ONE,
        )
        UnitAssignment.objects.create(
            lecturer=self.lecturer,
            unit=unassigned_unit,
        )
        result = Result.objects.create(
            student=self.student,
            unit=unassigned_unit,
            session=self.session,
            marks=90,
        )
        form = ResultEntryForm(lecturer=self.lecturer)

        self.assertNotIn(unassigned_unit, form.fields['unit'].queryset)
        self.assertIsNone(calculate_gpa(self.student, result.session))
        self.assertIsNone(calculate_cgpa(self.student))

    def test_results_from_another_course_do_not_affect_gpa(self):
        other_course = Course.objects.create(
            course_code='CSC202',
            course_name='Information Systems',
            duration=Course.Duration.THREE_YEARS,
            faculty=self.faculty,
        )
        other_student = Student.objects.create(
            reg_no='REG002',
            student_name='Other Student',
            gender=Student.Gender.MALE,
            contact='0700000001',
            course=other_course,
            faculty=self.faculty,
        )
        Result.objects.create(
            student=other_student,
            unit=self.unit,
            session=self.session,
            marks=90,
        )

        self.assertIsNone(calculate_gpa(other_student, self.session))
        self.assertIsNone(calculate_cgpa(other_student))
