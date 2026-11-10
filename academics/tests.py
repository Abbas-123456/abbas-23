from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from .access import ROLE_COORDINATOR, ROLE_LECTURER, ROLE_REGISTRAR
from .models import (
    Course,
    CourseUnit,
    Faculty,
    Grading,
    Lecturer,
    Result,
    Student,
    StudySession,
    UnitAssignment,
)
from .services import calculate_weighted_gpa, is_first_class
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

    def test_dashboard_uses_static_styles_and_live_academic_counts(self):
        response = self.client.get(reverse('academics:index'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '/static/academics/css/app.css')
        self.assertContains(response, '/static/academics/css/dashboard.css')
        self.assertContains(response, 'bootstrap-icons')
        self.assertContains(response, 'Recorded results')
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

    def test_deleting_referenced_faculty_shows_message(self):
        faculty = Faculty.objects.create(faculty_id=1, faculty_name='Science')
        Course.objects.create(
            course_code='CSC101',
            course_name='Computer Science',
            duration='03:00:00',
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
            duration='03:00:00',
            faculty=self.faculty,
        )
        self.student = Student.objects.create(
            reg_no='REG001',
            student_name='Amina Student',
            gender=Student.Gender.FEMALE,
            contact='0700000000',
            course=self.course,
        )
        self.session = StudySession.objects.create(
            academic_year='2025/2026',
            semester=StudySession.Semester.ONE,
            status=StudySession.Status.ONGOING,
        )
        self.unit = CourseUnit.objects.create(
            unit_name='Programming',
            credit_units=4,
            academic_year='2025/2026',
            semester=CourseUnit.Semester.ONE,
        )
        self.other_unit = CourseUnit.objects.create(
            unit_name='Calculus',
            credit_units=6,
            academic_year='2025/2026',
            semester=CourseUnit.Semester.ONE,
        )
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
        )
        UnitAssignment.objects.create(lecturer=self.lecturer, unit=self.unit)
        UnitAssignment.objects.create(lecturer=self.lecturer, unit=self.other_unit)
        Grading.objects.create(
            min_marks=0,
            max_marks=39,
            grade_symbol='F',
            grade_points=0,
        )
        Grading.objects.create(
            min_marks=40,
            max_marks=59,
            grade_symbol='C',
            grade_points=3,
        )
        Grading.objects.create(
            min_marks=60,
            max_marks=69,
            grade_symbol='B',
            grade_points=4,
        )
        Grading.objects.create(
            min_marks=70,
            max_marks=100,
            grade_symbol='A',
            grade_points=5,
        )

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
            marks=75,
        )
        Result.objects.create(
            student=self.student,
            unit=self.other_unit,
            session=self.session,
            marks=65,
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
        self.assertContains(response, '4.4')

        response = self.client.get(
            reverse('academics:model-update', args=['results', result.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_weighted_gpa_uses_unit_credits_and_first_class_cutoff(self):
        Result.objects.create(
            student=self.student,
            unit=self.other_unit,
            session=self.session,
            marks=65,
        )
        Result.objects.create(
            student=self.student,
            unit=self.unit,
            session=self.session,
            marks=90,
        )

        gpa = calculate_weighted_gpa(self.student)

        self.assertEqual(gpa, 4.4)
        self.assertTrue(is_first_class(gpa))
        self.assertFalse(is_first_class(4.39))
        self.assertFalse(is_first_class(None))
