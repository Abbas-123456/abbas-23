from django.conf import settings
from django.db import models
from django.db.models import Q


class Faculty(models.Model):
    faculty_id = models.IntegerField(primary_key=True, db_column='FacultyId')
    faculty_name = models.CharField(max_length=30, db_column='FacultyName')

    class Meta:
        db_table = 'FACULTY'

    def __str__(self):
        return self.faculty_name


class Course(models.Model):
    course_code = models.CharField(max_length=10, primary_key=True, db_column='CourseCode')
    course_name = models.CharField(max_length=50, db_column='CourseName')
    duration = models.TimeField(db_column='Duration')
    faculty = models.ForeignKey(
        Faculty,
        on_delete=models.PROTECT,
        db_column='FacultyId',
        related_name='courses',
    )

    class Meta:
        db_table = 'COURSE'

    def __str__(self):
        return self.course_name


class Student(models.Model):
    class Gender(models.TextChoices):
        MALE = 'M', 'Male'
        FEMALE = 'F', 'Female'

    student_id = models.AutoField(primary_key=True, db_column='StudentId')
    reg_no = models.CharField(max_length=30, db_column='Reg_No')
    student_name = models.CharField(max_length=50, db_column='StudentName')
    gender = models.CharField(max_length=1, choices=Gender.choices, db_column='Gender')
    contact = models.CharField(max_length=10, db_column='Contact')
    course = models.ForeignKey(
        Course,
        on_delete=models.PROTECT,
        db_column='CourseCode',
        related_name='students',
    )
    date_of_birth = models.DateField(null=True, blank=True, db_column='DATE_OF_BIRTH')

    class Meta:
        db_table = 'STUDENT'

    def __str__(self):
        return self.student_name


class Lecturer(models.Model):
    class Gender(models.TextChoices):
        MALE = 'M', 'Male'
        FEMALE = 'F', 'Female'

    lecturer_id = models.AutoField(primary_key=True, db_column='LecturerId')
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lecturer_profile',
    )
    lecturer_name = models.CharField(max_length=50, db_column='LecturerName')
    gender = models.CharField(max_length=1, choices=Gender.choices, db_column='Gender')
    contact = models.CharField(max_length=10, db_column='Contact')
    department = models.CharField(max_length=50, db_column='Department')

    class Meta:
        db_table = 'LECTURER'

    def __str__(self):
        return self.lecturer_name


class CourseUnit(models.Model):
    class Semester(models.TextChoices):
        ONE = '1', 'Semester 1'
        TWO = '2', 'Semester 2'

    unit_code = models.AutoField(primary_key=True, db_column='UnitCode')
    unit_name = models.CharField(max_length=30, db_column='UnitName')
    credit_units = models.IntegerField(db_column='CreditUnits')
    academic_year = models.CharField(max_length=9, db_column='AcademicYear')
    semester = models.CharField(max_length=1, choices=Semester.choices, db_column='Semester')
    lecturers = models.ManyToManyField(
        'Lecturer',
        through='UnitAssignment',
        related_name='course_units',
        blank=True,
    )

    class Meta:
        db_table = 'COURSEUNIT'

    def __str__(self):
        return self.unit_name


class UnitAssignment(models.Model):
    lecturer = models.ForeignKey(
        Lecturer,
        on_delete=models.CASCADE,
        related_name='unit_assignments',
    )
    unit = models.ForeignKey(
        CourseUnit,
        on_delete=models.CASCADE,
        related_name='lecturer_assignments',
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('lecturer', 'unit'),
                name='uniq_lecturer_course_unit',
            ),
        ]

    def __str__(self):
        return f'{self.lecturer} - {self.unit}'


class StudySession(models.Model):
    class Semester(models.TextChoices):
        ONE = '1', 'Semester 1'
        TWO = '2', 'Semester 2'

    class Status(models.TextChoices):
        ONGOING = 'Ongoing', 'Ongoing'
        COMPLETED = 'Completed', 'Completed'

    session_id = models.AutoField(primary_key=True, db_column='SessionId')
    academic_year = models.CharField(max_length=10, db_column='Academic_Year')
    semester = models.CharField(max_length=1, choices=Semester.choices, db_column='Semester')
    status = models.CharField(max_length=9, choices=Status.choices, db_column='Status')

    class Meta:
        db_table = 'STUDYSESSION'

    def __str__(self):
        return f'{self.academic_year} semester {self.semester}'


class Grading(models.Model):
    grade_id = models.AutoField(primary_key=True, db_column='GradeId')
    min_marks = models.IntegerField(db_column='Min_Marks')
    max_marks = models.IntegerField(db_column='Max_Marks')
    grade_symbol = models.CharField(max_length=1, db_column='Grade_Symbol')
    grade_points = models.IntegerField(db_column='Grade_Points')

    class Meta:
        db_table = 'GRADING'

    def __str__(self):
        return self.grade_symbol


class Timetable(models.Model):
    class Semester(models.TextChoices):
        ONE = '1', 'Semester 1'
        TWO = '2', 'Semester 2'

    timetable_id = models.AutoField(primary_key=True, db_column='TimetableId')
    day = models.DateField(db_column='Day')
    time = models.TimeField(db_column='Time')
    room = models.CharField(max_length=20, db_column='Room')
    semester = models.CharField(max_length=1, choices=Semester.choices, db_column='Semester')
    unit = models.ForeignKey(
        CourseUnit,
        on_delete=models.PROTECT,
        db_column='UnitCode',
        related_name='timetable_entries',
    )
    lecturer = models.ForeignKey(
        Lecturer,
        on_delete=models.PROTECT,
        db_column='LecturerId',
        related_name='timetable_entries',
    )

    class Meta:
        db_table = 'TIMETABLE'

    def __str__(self):
        return f'{self.unit} - {self.day}'


class Result(models.Model):
    result_id = models.AutoField(primary_key=True, db_column='ResultId')
    student = models.ForeignKey(
        Student,
        on_delete=models.PROTECT,
        db_column='StudentId',
        related_name='results',
    )
    unit = models.ForeignKey(
        CourseUnit,
        on_delete=models.PROTECT,
        db_column='UnitCode',
        related_name='results',
    )
    session = models.ForeignKey(
        StudySession,
        on_delete=models.PROTECT,
        db_column='SessionId',
        related_name='results',
    )
    entered_by = models.ForeignKey(
        Lecturer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='entered_results',
    )
    marks = models.IntegerField(db_column='Marks')

    class Meta:
        db_table = 'RESULTS'
        constraints = [
            models.UniqueConstraint(
                fields=('student', 'unit', 'session'),
                name='uniq_result_stu_unit_sess',
            ),
            models.CheckConstraint(
                condition=Q(marks__gte=0, marks__lte=100),
                name='result_marks_0_100',
            ),
        ]

    def __str__(self):
        return f'{self.student} - {self.unit}: {self.marks}'
