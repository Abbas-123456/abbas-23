from django.urls import path

from . import views

app_name = 'academics'

urlpatterns = [
    path('', views.index, name='index'),
    path('<slug:model_name>/', views.model_list, name='model-list'),
    path('<slug:model_name>/create/', views.model_form, name='model-create'),
    path('<slug:model_name>/<str:pk>/', views.model_detail, name='model-detail'),
    path(
        '<slug:model_name>/<str:pk>/edit/',
        views.model_form,
        name='model-update',
    ),
    path(
        '<slug:model_name>/<str:pk>/delete/',
        views.model_delete,
        name='model-delete',
    ),
]
