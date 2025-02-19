from django import forms
from .models import Pedido, Transferencia, Sucursal, Perfil
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

class PedidoForm(forms.ModelForm):
    class Meta:
        model = Pedido
        fields = ['medicamento', 'cantidad', 'opcion_entrega']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['opcion_entrega'].label = "Opción de Entrega"


class TransferenciaForm(forms.ModelForm):
    """Formulario de transferencia SIN el campo de sucursal de origen (se asigna automáticamente en la vista)."""

    class Meta:
        model = Transferencia
        fields = ['medicamento', 'sucursal_destino', 'cantidad']  # ✅ Eliminamos 'sucursal_origen'

    def __init__(self, *args, usuario=None, **kwargs):
        """Evita mostrar la sucursal de origen y solo permite elegir destino."""
        super().__init__(*args, **kwargs)

        self.fields['sucursal_destino'].label = "Sucursal de Destino"
        self.fields['medicamento'].label = "Medicamento"
        self.fields['cantidad'].label = "Cantidad"

        # ✅ Filtramos las sucursales para excluir la del empleado si se pasó un usuario
        if usuario and hasattr(usuario, 'perfil') and usuario.perfil.sucursal:
            self.fields['sucursal_destino'].queryset = Sucursal.objects.exclude(id=usuario.perfil.sucursal.id)


class RegistroForm(UserCreationForm):
    email = forms.EmailField(required=True)
    sucursal = forms.ModelChoiceField(
        queryset=Sucursal.objects.all(),
        required=True,
        label="Sucursal de Preferencia"
    )
    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2', 'sucursal']

