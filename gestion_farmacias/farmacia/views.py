from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import Medicamento, Inventario, Pedido, Sucursal, Transferencia, Perfil
from .forms import PedidoForm, TransferenciaForm, RegistroForm
from django.contrib.auth.models import User
from .models import HistorialStock

# Verifica si el usuario es administrador
def es_admin(user):
    return user.is_authenticated and getattr(user, 'perfil', None) and user.perfil.rol == 'admin'

# Verifica si el usuario es empleado
def es_empleado(user):
    return user.is_authenticated and getattr(user, 'perfil', None) and user.perfil.rol == 'empleado'

# Verifica si el usuario es cliente
def es_cliente(user):
    return user.is_authenticated and getattr(user, 'perfil', None) and user.perfil.rol == 'cliente'

def inicio(request):
    """Redirige a /admin si el usuario autenticado es administrador, de lo contrario muestra la interfaz normal."""
    if request.user.is_authenticated:
        perfil = getattr(request.user, 'perfil', None)
        if request.user.is_superuser or (perfil and perfil.rol == 'admin'):
            return redirect('/admin/')
    return render(request, 'farmacia/inicio.html')


def registro(request):
    if request.method == 'POST':
        form = RegistroForm(request.POST)
        if form.is_valid():
            usuario = form.save()
            sucursal = form.cleaned_data['sucursal']
            Perfil.objects.create(usuario=usuario, rol='cliente', sucursal=sucursal)
            messages.success(request, 'Registro exitoso. Ahora puedes iniciar sesión.')
            return redirect('login')
        else:
            messages.error(request, 'Hubo un error en el registro. Por favor verifica los datos ingresados.')
    else:
        form = RegistroForm()
    return render(request, 'farmacia/registro.html', {'form': form})


@login_required
@user_passes_test(lambda u: es_empleado(u) or es_admin(u))
def ver_inventario(request):
    inventario = Inventario.objects.all()
    return render(request, 'farmacia/inventario.html', {'inventario': inventario})


@login_required
def mis_pedidos(request):
    pedidos = Pedido.objects.filter(cliente=request.user).select_related('sucursal_envio')

    for pedido in pedidos:
        # Verifica si existe una transferencia pendiente relacionada con el pedido
        pedido.transferencia_pendiente = Transferencia.objects.filter(
            medicamento=pedido.medicamento,
            sucursal_destino=pedido.sucursal_solicitada,
            estado='pendiente'
        ).exists()

    return render(request, 'farmacia/mis_pedidos.html', {'pedidos': pedidos})


@login_required
@user_passes_test(es_cliente)
def realizar_pedido(request, medicamento_id):
    medicamento = get_object_or_404(Medicamento, id=medicamento_id)
    sucursal_cliente = request.user.perfil.sucursal

    # 📌 Verifica el stock en la sucursal del cliente
    inventario_cliente = Inventario.objects.filter(medicamento=medicamento, sucursal=sucursal_cliente).first()
    stock_cliente = inventario_cliente.cantidad if inventario_cliente else 0

    # 📌 Obtiene el stock en otras sucursales
    sucursales_disponibles = Inventario.objects.filter(medicamento=medicamento, cantidad__gt=0).exclude(sucursal=sucursal_cliente)
    stock_total_otras_sucursales = sum([item.cantidad for item in sucursales_disponibles])

    # 📌 Stock total disponible en todas las sucursales
    stock_total_disponible = stock_cliente + stock_total_otras_sucursales

    if request.method == 'POST':
        cantidad_solicitada = int(request.POST.get('cantidad'))
        opcion_entrega = request.POST.get('opcion_entrega', 'retiro_sucursal')

        # 📌 Caso 1: La sucursal del cliente tiene suficiente stock
        if stock_cliente >= cantidad_solicitada:
            inventario_cliente.ajustar_stock(-cantidad_solicitada)

            Pedido.objects.create(
                cliente=request.user,
                medicamento=medicamento,
                sucursal_solicitada=sucursal_cliente,
                cantidad=cantidad_solicitada,
                estado="completado",
                opcion_entrega=opcion_entrega
            )

            messages.success(request, 'Pedido realizado y completado con éxito.')
            return redirect('mis_pedidos')

        # 📌 Caso 2: Stock total en otras sucursales puede completar el pedido
        elif stock_total_disponible >= cantidad_solicitada:
            cantidad_faltante = cantidad_solicitada - stock_cliente
            sucursal_envio = sucursales_disponibles.first().sucursal  # Selecciona la primera sucursal disponible

            # 📌 Se crea el pedido en estado pendiente
            pedido = Pedido.objects.create(
                cliente=request.user,
                medicamento=medicamento,
                sucursal_solicitada=sucursal_cliente,
                sucursal_envio=sucursal_envio,
                cantidad=cantidad_solicitada,
                estado="pendiente",
                opcion_entrega=opcion_entrega
            )

            # 📌 Se genera la transferencia desde la sucursal con stock
            transferencia = Transferencia.objects.create(
                medicamento=medicamento,
                sucursal_origen=sucursal_envio,
                sucursal_destino=sucursal_cliente,
                cantidad=cantidad_faltante,
                estado="pendiente",
                pedido_relacionado=pedido
            )

            messages.info(request, f'Se solicitará una transferencia de {cantidad_faltante} unidades desde {sucursal_envio.nombre}.')
            return redirect('mis_pedidos')

        # 📌 Caso 3: No hay suficiente stock en ninguna sucursal
        else:
            messages.error(request, 'No hay suficiente stock en ninguna sucursal para completar su pedido.')
            return redirect('listar_medicamentos')

    return render(request, 'farmacia/pedido.html', {
        'medicamento': medicamento,
        'inventario': inventario_cliente,
        'sucursales_disponibles': sucursales_disponibles
    })


@login_required
@user_passes_test(es_empleado)
def gestionar_transferencias(request):
    transferencias_pendientes = Transferencia.objects.filter(estado='pendiente')

    if request.method == 'POST':
        transferencia_id = request.POST.get('transferencia_id')
        accion = request.POST.get('accion')
        transferencia = get_object_or_404(Transferencia, id=transferencia_id)

        if accion == 'aprobar':
            transferencia.aprobar_transferencia()
            messages.success(request, f'Transferencia de {transferencia.cantidad} unidades aprobada.')
        elif accion == 'rechazar':
            transferencia.rechazar_transferencia()
            messages.warning(request, 'Transferencia rechazada y pedido cancelado.')

        return redirect('gestionar_transferencias')

    return render(request, 'farmacia/gestionar_transferencias.html', {'transferencias_pendientes': transferencias_pendientes})


@login_required
@user_passes_test(es_empleado)
def transferencias_manual(request):
    """Permite a los empleados realizar transferencias entre sucursales sin necesidad de un pedido."""
    empleado = request.user
    sucursal_origen = empleado.perfil.sucursal  # ✅ Se asigna la sucursal del empleado

    if request.method == 'POST':
        form = TransferenciaForm(request.POST, usuario=empleado)
        if form.is_valid():
            transferencia = form.save(commit=False)
            transferencia.sucursal_origen = sucursal_origen  # ✅ Se asigna automáticamente la sucursal de origen

            # ❌ Nueva Validación: Bloquea transferencias a la misma sucursal
            if transferencia.sucursal_origen == transferencia.sucursal_destino:
                messages.error(request, "No puedes transferir medicamentos a la misma sucursal.")
                return redirect('transferencias_manual')

            transferencia.estado = "aprobada"  # ✅ Se aprueba automáticamente

            inventario_origen = Inventario.objects.filter(
                medicamento=transferencia.medicamento,
                sucursal=sucursal_origen
            ).first()

            # ✅ Se obtiene el inventario de la sucursal de destino
            inventario_destino, created = Inventario.objects.get_or_create(
                medicamento=transferencia.medicamento,
                sucursal=transferencia.sucursal_destino,
                defaults={'cantidad': 0}
            )

            if inventario_origen and inventario_origen.tiene_stock_suficiente(transferencia.cantidad):
                # ✅ Ahora sí pasamos correctamente el objeto Inventario
                inventario_origen.transferir_stock(inventario_destino, transferencia.cantidad)

                transferencia.save()
                messages.success(request,
                                 f'Transferencia de {transferencia.cantidad} unidades de {transferencia.medicamento} realizada con éxito.')
                return redirect('historial_transferencias')

            else:
                messages.error(request,
                               'No hay suficiente stock en la sucursal de origen para realizar la transferencia.')

    else:
        # ❗ FALLO ANTERIOR: No se estaba pasando `usuario=empleado`
        form = TransferenciaForm(usuario=empleado)  # ✅ Se pasa el usuario para filtrar las sucursales

    return render(request, 'farmacia/transferencias_manual.html', {'form': form})


@login_required
@user_passes_test(es_empleado)
def historial_transferencias(request):
    transferencias = Transferencia.objects.all().order_by('-fecha')
    return render(request, 'farmacia/historial_transferencias.html', {'transferencias': transferencias})


@login_required
@user_passes_test(es_empleado)
def gestionar_clientes_pedidos(request):
    clientes = User.objects.filter(perfil__rol='cliente').prefetch_related('perfil', 'pedido_set')
    return render(request, 'farmacia/gestionar_clientes_pedidos.html', {'clientes': clientes})

@login_required
@user_passes_test(es_cliente)
def listar_medicamentos(request):
    sucursal_actual = request.user.perfil.sucursal
    inventarios = Inventario.objects.filter(sucursal=sucursal_actual)
    return render(request, 'farmacia/lista_medicamentos.html', {'inventarios': inventarios})


@login_required
@user_passes_test(es_empleado)
def aumentar_stock(request, inventario_id):
    """
    Permite a los empleados aumentar el stock de medicamentos en su sucursal.
    """
    inventario = get_object_or_404(Inventario, id=inventario_id)

    if request.method == 'POST':
        cantidad = int(request.POST.get('cantidad', 0))

        if cantidad > 0:
            inventario.aumentar_stock(cantidad, request.user)
            messages.success(request, f'Se añadieron {cantidad} unidades de {inventario.medicamento.nombre}.')
        else:
            messages.error(request, 'La cantidad debe ser mayor a 0.')

        return redirect('ver_inventario')

    return render(request, 'farmacia/aumentar_stock.html', {'inventario': inventario})


@login_required
@user_passes_test(es_empleado)
def ver_historial_stock(request):
    """Muestra el historial de ajustes de stock realizados por los empleados."""
    historial = HistorialStock.objects.select_related('inventario', 'empleado').order_by('-fecha')
    return render(request, 'farmacia/historial_stock.html', {'historial': historial})
