from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from .models import Course, Faculty
from .views import MODEL_REGISTRY


class AcademicCrudViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='staff',
            password='test-password-123',
        )
        self.client.force_login(self.user)

    def test_all_model_lists_and_create_forms_are_accessible(self):
        for model_name in MODEL_REGISTRY:
            with self.subTest(model_name=model_name):
                for url_name in ('model-list', 'model-create'):
                    response = self.client.get(
                        reverse(f'academics:{url_name}', args=[model_name])
                    )
                    self.assertEqual(response.status_code, 200)

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

        self.assertRedirects(response, reverse('academics:index'))
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
