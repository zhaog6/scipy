"""Iterative methods for solving linear systems"""

__all__ = ['bicg','bicgstab','cg','cgs','gmres','qmr','cgne','cgnr','icgs']

import warnings
import numpy as np

from . import _iterative

from scipy.sparse.linalg.interface import LinearOperator
from .utils import make_system
from scipy._lib._util import _aligned_zeros
from scipy._lib._threadsafety import non_reentrant

_type_conv = {'f':'s', 'd':'d', 'F':'c', 'D':'z'}


# Part of the docstring common to all iterative solvers
common_doc1 = \
"""
Parameters
----------
A : {sparse matrix, dense matrix, LinearOperator}"""

common_doc2 = \
"""b : {array, matrix}
    Right hand side of the linear system. Has shape (N,) or (N,1).

Returns
-------
x : {array, matrix}
    The converged solution.
info : integer
    Provides convergence information:
        0  : successful exit
        >0 : convergence to tolerance not achieved, number of iterations
        <0 : illegal input or breakdown

Other Parameters
----------------
x0  : {array, matrix}
    Starting guess for the solution.
tol, atol : float, optional
    Tolerances for convergence, ``norm(residual) <= max(tol*norm(b), atol)``.
    The default for ``atol`` is ``'legacy'``, which emulates
    a different legacy behavior.

    .. warning::

       The default value for `atol` will be changed in a future release.
       For future compatibility, specify `atol` explicitly.
maxiter : integer
    Maximum number of iterations.  Iteration will stop after maxiter
    steps even if the specified tolerance has not been achieved.
M : {sparse matrix, dense matrix, LinearOperator}
    Preconditioner for A.  The preconditioner should approximate the
    inverse of A.  Effective preconditioning dramatically improves the
    rate of convergence, which implies that fewer iterations are needed
    to reach a given error tolerance.
callback : function
    User-supplied function to call after each iteration.  It is called
    as callback(xk), where xk is the current solution vector.

"""


def _stoptest(residual, atol):
    """
    Successful termination condition for the solvers.
    """
    resid = np.linalg.norm(residual)
    if resid <= atol:
        return resid, 1
    else:
        return resid, 0


def _get_atol(tol, atol, bnrm2, get_residual, routine_name):
    """
    Parse arguments for absolute tolerance in termination condition.

    Parameters
    ----------
    tol, atol : object
        The arguments passed into the solver routine by user.
    bnrm2 : float
        2-norm of the rhs vector.
    get_residual : callable
        Callable ``get_residual()`` that returns the initial value of
        the residual.
    routine_name : str
        Name of the routine.
    """

    if atol is None:
        warnings.warn("scipy.sparse.linalg.{name} called without specifying `atol`. "
                      "The default value will be changed in a future release. "
                      "For compatibility, specify a value for `atol` explicitly, e.g., "
                      "``{name}(..., atol=0)``, or to retain the old behavior "
                      "``{name}(..., atol='legacy')``".format(name=routine_name),
                      category=DeprecationWarning, stacklevel=4)
        atol = 'legacy'

    tol = float(tol)

    if atol == 'legacy':
        # emulate old legacy behavior
        resid = get_residual()
        if resid <= tol:
            return 'exit'
        if bnrm2 == 0:
            return tol
        else:
            return tol * float(bnrm2)
    else:
        return max(float(atol), tol * float(bnrm2))


def set_docstring(header, Ainfo, footer='', atol_default='0'):
    def combine(fn):
        fn.__doc__ = '\n'.join((header, common_doc1,
                                '    ' + Ainfo.replace('\n', '\n    '),
                                common_doc2, footer))
        return fn
    return combine


#======================
#   BiCG
#======================
@set_docstring('Use BIConjugate Gradient iteration to solve ``Ax = b``.',
               'The real or complex N-by-N matrix of the linear system.\n'
               'Alternatively, ``A`` can be a linear operator which can\n'
               'produce ``Ax`` and ``A^T x`` using, e.g.,\n'
               '``scipy.sparse.linalg.LinearOperator``.',
               footer="""
               
               Examples
               --------
               >>> from scipy.sparse import csc_matrix
               >>> from scipy.sparse.linalg import bicg
               >>> A = csc_matrix([[3, 2, 0], [1, -1, 0], [0, 5, 1]], dtype=float)
               >>> b = np.array([2, 4, -1], dtype=float)
               >>> x, exitCode = bicg(A, b)
               >>> print(exitCode)            # 0 indicates successful convergence
               0
               >>> np.allclose(A.dot(x), b)
               True
               
               """
               )
@non_reentrant()
def bicg(A, b, x0=None, tol=1e-5, maxiter=None, M=None, callback=None, atol=None):
    if not (A.shape[0] == A.shape[1] and A.shape[0] == len(b)):
        raise ValueError("The size of the matrix and the right-hand side does not match.")
    if maxiter is None:
        maxiter = 10000
    # type judgment and conversion
    dtype = A.dtype
    if dtype == int:
        dtype = float
        A = A.astype(dtype)
        if b.dtype == int:
            b = b.astype(dtype)
    A, M, x, b, postprocess = make_system(A, M, x0, b)
    # judge if b is a zero vector
    if np.linalg.norm(b) == 0.:
        x = b.copy()
        return (postprocess(x), 0)
    At = A.H
    Mt = M.H
    r = b - A.matvec(x)
    z = M.matvec(r)
    rhat = z.copy()
    z_hat = Mt.matvec(rhat)
    d_old = np.inner(rhat.conjugate(), z)
    p = r.copy()
    p_hat = z.copy()
    beta = 0.
    r0norm = np.linalg.norm(r)
    if r0norm == 0.:
        return (postprocess(x), 0)
    if atol is not None:
        if atol == 'legacy':
            if r0norm <= tol:
                return postprocess(x), 0
        else:
            tol = max(float(atol)/r0norm, tol)
    for iter in range(maxiter):
        p = z + beta * p
        p_hat = z_hat + beta.conjugate() * p_hat
        Ap = A.matvec(p)
        phattAp = np.inner(p_hat.conjugate(), Ap)
        if phattAp == 0.:
            return (postprocess(x), -1)
        alpha = d_old / phattAp
        x += alpha * p
        r -= alpha * Ap
        beta = np.linalg.norm(r) / r0norm
        if callback is not None:
            callback(x)
        if beta < tol:
            return (postprocess(x), 0)
        elif iter == maxiter - 1:
            return (postprocess(x), maxiter)
        Ap = At.matvec(p_hat)
        rhat -= alpha.conjugate() * Ap  # alpha * At * p_hat
        z = M.matvec(r)
        d = np.inner(rhat.conjugate(), z)
        if d == 0.:
            return (postprocess(x), -1)
        beta = d / d_old
        d_old = d.copy()
        z_hat = Mt.matvec(rhat)


#======================
#   BiCGSTAB
#======================
@set_docstring('Use BIConjugate Gradient STABilized iteration to solve '
               '``Ax = b``.',
               'The real or complex N-by-N matrix of the linear system.\n'
               'Alternatively, ``A`` can be a linear operator which can\n'
               'produce ``Ax`` using, e.g.,\n'
               '``scipy.sparse.linalg.LinearOperator``.')
@non_reentrant()
def bicgstab(A, b, x0=None, tol=1e-5, maxiter=None, M=None, callback=None, atol=None):
    if not (A.shape[0] == A.shape[1] and A.shape[0] == len(b)):
        raise ValueError("The size of the matrix and the right-hand side does not match.")
    if maxiter is None:
        maxiter = 10000
    # type judgment and conversion
    dtype = A.dtype
    if dtype == int:
        dtype = float
        A = A.astype(dtype)
        if b.dtype == int:
            b = b.astype(dtype)
    A, M, x, b, postprocess = make_system(A, M, x0, b)
    # judge if b is a zero vector
    if np.linalg.norm(b) == 0.:
        x = b.copy()
        return (postprocess(x), 0)
    r = b - A.matvec(x)
    rhat = r.copy()
    r0norm = np.linalg.norm(r)
    if r0norm == 0.:
        return (postprocess(x), 0)
    if atol is not None:
        if atol == 'legacy':
            if r0norm <= tol:
                return postprocess(x), 0
        else:
            tol = max(float(atol)/r0norm, tol)
    for iter in range(maxiter):
        rho1 = np.inner(rhat.conjugate(), r)
        if rho1 == 0.:
            print("Iterative method failed due to inner product of residuals is zero")
        if iter == 0:
            p = r.copy()
        else:
            beta = (rho1/rho0) * (alpha/omega)
            p = r + beta * (p - omega*v)
        p_hat = M.matvec(p)
        v = A.matvec(p_hat)
        rhattv = np.inner(rhat.conjugate(), v)
        if rhattv == 0.:
            return (postprocess(x), -1)
        alpha = rho1 / rhattv
        s = r - alpha * v
        if np.linalg.norm(s) < 1e-14:
            x += alpha * p_hat
            return (postprocess(x), 0)
        s_hat = M.matvec(s)
        t = A.matvec(s_hat)
        omega = np.inner(t.conjugate(), s) / np.inner(t.conjugate(), t)
        x += alpha * p_hat + omega * s_hat
        r = s - omega * t
        beta = np.linalg.norm(r) / r0norm
        if callback is not None:
            callback(x)
        if beta < tol:
            return (postprocess(x), 0)
        elif iter == maxiter - 1:
            return (postprocess(x), maxiter)
        rho0 = rho1;


#======================
#   CG
#======================
@set_docstring('Use Conjugate Gradient iteration to solve ``Ax = b``.',
               'The real or complex N-by-N matrix of the linear system.\n'
               '``A`` must represent a hermitian, positive definite matrix.\n'
               'Alternatively, ``A`` can be a linear operator which can\n'
               'produce ``Ax`` using, e.g.,\n'
               '``scipy.sparse.linalg.LinearOperator``.')
@non_reentrant()
def cg(A, b, x0=None, tol=1e-5, maxiter=None, M=None, callback=None, atol=None):
    if not (A.shape[0] == A.shape[1] and A.shape[0] == len(b)):
        raise ValueError("The size of the matrix and the right-hand side does not match.")
    if maxiter is None:
        maxiter = 10000
    # type judgment and conversion
    dtype = A.dtype
    if dtype == int:
        dtype = float
        A = A.astype(dtype)
        if b.dtype == int:
            b = b.astype(dtype)
    A, M, x, b, postprocess = make_system(A, M, x0, b)
    # judge if b is a zero vector
    if np.linalg.norm(b) == 0.:
        x = b.copy()
        return (postprocess(x), 0)
    r = b - A.matvec(x)  # A is a LinearOperator
    z = M.matvec(r)  # z = M * r
    p = z.copy()
    r0norm = np.linalg.norm(r)
    if r0norm == 0.:
        return (postprocess(x), 0)
    if atol is not None:
        if atol == 'legacy':
            if r0norm <= tol:
                return postprocess(x), 0
        else:
            tol = max(float(atol)/r0norm, tol)
    for iter in range(maxiter):
        rho0 = np.inner(r.conjugate(), z)
        q = A.matvec(p)
        ptq = np.inner(p.conjugate(), q)
        if ptq == 0.:
            return (postprocess(x), -1)
        alpha = rho0 / ptq
        x += alpha * p
        r -= alpha * q
        alpha = np.linalg.norm(r) / r0norm
        if callback is not None:
            callback(x)
        if alpha < tol:
            return (postprocess(x), 0)
        elif iter == maxiter - 1:
            return (postprocess(x), maxiter)
        z = M.matvec(r)
        rho1 = np.inner(r.conjugate(), z)
        alpha = rho1 / rho0
        p = z + alpha * p


#======================
#   Traditional CGS
#======================
@set_docstring('Use Conjugate Gradient Squared iteration to solve ``Ax = b``.',
               'The real-valued N-by-N matrix of the linear system.\n'
               'Alternatively, ``A`` can be a linear operator which can\n'
               'produce ``Ax`` using, e.g.,\n'
               '``scipy.sparse.linalg.LinearOperator``.')
@non_reentrant()
def cgs(A, b, x0=None, tol=1e-5, maxiter=None, M=None, callback=None, atol=None):
    if not (A.shape[0] == A.shape[1] and A.shape[0] == len(b)):
        raise ValueError("The size of the matrix and the right-hand side does not match.")
    if maxiter is None:
        maxiter = 10000
    # type judgment and conversion
    dtype = A.dtype
    if dtype == int:
        dtype = float
        A = A.astype(dtype)
        if b.dtype == int:
            b = b.astype(dtype)
    A, M, x, b, postprocess = make_system(A, M, x0, b)
    # judge if b is a zero vector
    if np.linalg.norm(b) == 0.:
        x = b.copy()
        return (postprocess(x), 0)
    r = b - A.matvec(x)
    rhat = r.copy()
    d_old = np.inner(rhat.conjugate(), r)
    p = r.copy()
    q = r.copy()
    beta = 0.
    r0norm = np.linalg.norm(r)
    if r0norm == 0.:
        return (postprocess(x), 0)
    if atol is not None:
        if atol == 'legacy':
            if r0norm <= tol:
                return postprocess(x), 0
        else:
            tol = max(float(atol)/r0norm, tol)
    for iter in range(maxiter):
        w = r + beta * q
        p = w + beta * q + (beta**2) * p
        z = M.matvec(p)
        Az = A.matvec(z)
        rhattAz = np.inner(rhat.conjugate(), Az)
        if rhattAz == 0.:
            return (postprocess(x), -1)
        alpha = d_old / rhattAz
        q = w - alpha * Az
        w += q
        z = alpha * M.matvec(w)
        x += z
        r -= A.matvec(z)
        alpha = np.linalg.norm(r) / r0norm
        if callback is not None:
            callback(x)
        if alpha < tol:
            return (postprocess(x), 0)
        elif iter == maxiter - 1:
            return (postprocess(x), maxiter)
        d = np.inner(rhat.conjugate(), r)
        if d == 0.:
            return (postprocess(x), -1)
        beta = d / d_old
        d_old = d


#======================
#   Restarted GMRES
#======================
@non_reentrant()
def gmres(A, b, x0=None, tol=1e-5, restart=None, maxiter=None, M=None, callback=None,
          restrt=None, atol=None, callback_type=None):
    """
    Use Generalized Minimal RESidual iteration to solve ``Ax = b``.

    Parameters
    ----------
    A : {sparse matrix, dense matrix, LinearOperator}
        The real or complex N-by-N matrix of the linear system.
        Alternatively, ``A`` can be a linear operator which can
        produce ``Ax`` using, e.g.,
        ``scipy.sparse.linalg.LinearOperator``.
    b : {array, matrix}
        Right hand side of the linear system. Has shape (N,) or (N,1).

    Returns
    -------
    x : {array, matrix}
        The converged solution.
    info : int
        Provides convergence information:
          * 0  : successful exit
          * >0 : convergence to tolerance not achieved, number of iterations
          * <0 : illegal input or breakdown

    Other parameters
    ----------------
    x0 : {array, matrix}
        Starting guess for the solution (a vector of zeros by default).
    tol, atol : float, optional
        Tolerances for convergence, ``norm(residual) <= max(tol*norm(b), atol)``.
        The default for ``atol`` is ``'legacy'``, which emulates
        a different legacy behavior.

        .. warning::

           The default value for `atol` will be changed in a future release.
           For future compatibility, specify `atol` explicitly.
    restart : int, optional
        Number of iterations between restarts. Larger values increase
        iteration cost, but may be necessary for convergence.
        Default is 20.
    maxiter : int, optional
        Maximum number of iterations (restart cycles).  Iteration will stop
        after maxiter steps even if the specified tolerance has not been
        achieved.
    M : {sparse matrix, dense matrix, LinearOperator}
        Inverse of the preconditioner of A.  M should approximate the
        inverse of A and be easy to solve for (see Notes).  Effective
        preconditioning dramatically improves the rate of convergence,
        which implies that fewer iterations are needed to reach a given
        error tolerance.  By default, no preconditioner is used.
    callback : function
        User-supplied function to call after each iteration.  It is called
        as `callback(args)`, where `args` are selected by `callback_type`.
    callback_type : {'x', 'pr_norm', 'legacy'}, optional
        Callback function argument requested:
          - ``x``: current iterate (ndarray), called on every restart
          - ``pr_norm``: relative (preconditioned) residual norm (float),
            called on every inner iteration
          - ``legacy`` (default): same as ``pr_norm``, but also changes the
            meaning of 'maxiter' to count inner iterations instead of restart
            cycles.
    restrt : int, optional
        DEPRECATED - use `restart` instead.

    See Also
    --------
    LinearOperator

    Notes
    -----
    A preconditioner, P, is chosen such that P is close to A but easy to solve
    for. The preconditioner parameter required by this routine is
    ``M = P^-1``. The inverse should preferably not be calculated
    explicitly.  Rather, use the following template to produce M::

      # Construct a linear operator that computes P^-1 * x.
      import scipy.sparse.linalg as spla
      M_x = lambda x: spla.spsolve(P, x)
      M = spla.LinearOperator((n, n), M_x)

    Examples
    --------
    >>> from scipy.sparse import csc_matrix
    >>> from scipy.sparse.linalg import gmres
    >>> A = csc_matrix([[3, 2, 0], [1, -1, 0], [0, 5, 1]], dtype=float)
    >>> b = np.array([2, 4, -1], dtype=float)
    >>> x, exitCode = gmres(A, b)
    >>> print(exitCode)            # 0 indicates successful convergence
    0
    >>> np.allclose(A.dot(x), b)
    True
    """

    # Change 'restrt' keyword to 'restart'
    if restrt is None:
        restrt = restart
    elif restart is not None:
        raise ValueError("Cannot specify both restart and restrt keywords. "
                         "Preferably use 'restart' only.")

    if callback is not None and callback_type is None:
        # Warn about 'callback_type' semantic changes.
        # Probably should be removed only in far future, Scipy 2.0 or so.
        warnings.warn("scipy.sparse.linalg.gmres called without specifying `callback_type`. "
                      "The default value will be changed in a future release. "
                      "For compatibility, specify a value for `callback_type` explicitly, e.g., "
                      "``{name}(..., callback_type='pr_norm')``, or to retain the old behavior "
                      "``{name}(..., callback_type='legacy')``",
                      category=DeprecationWarning, stacklevel=3)

    if callback_type is None:
        callback_type = 'legacy'

    if callback_type not in ('x', 'pr_norm', 'legacy'):
        raise ValueError("Unknown callback_type: {!r}".format(callback_type))

    if callback is None:
        callback_type = 'none'

    A, M, x, b,postprocess = make_system(A, M, x0, b)

    n = len(b)
    if maxiter is None:
        maxiter = n*10

    if restrt is None:
        restrt = 20
    restrt = min(restrt, n)

    matvec = A.matvec
    psolve = M.matvec
    ltr = _type_conv[x.dtype.char]
    revcom = getattr(_iterative, ltr + 'gmresrevcom')

    bnrm2 = np.linalg.norm(b)
    Mb_nrm2 = np.linalg.norm(psolve(b))
    get_residual = lambda: np.linalg.norm(matvec(x) - b)
    atol = _get_atol(tol, atol, bnrm2, get_residual, 'gmres')
    if atol == 'exit':
        return postprocess(x), 0

    if bnrm2 == 0:
        return postprocess(b), 0

    # Tolerance passed to GMRESREVCOM applies to the inner iteration
    # and deals with the left-preconditioned residual.
    ptol_max_factor = 1.0
    ptol = Mb_nrm2 * min(ptol_max_factor, atol / bnrm2)
    resid = np.nan
    presid = np.nan
    ndx1 = 1
    ndx2 = -1
    # Use _aligned_zeros to work around a f2py bug in Numpy 1.9.1
    work = _aligned_zeros((6+restrt)*n,dtype=x.dtype)
    work2 = _aligned_zeros((restrt+1)*(2*restrt+2),dtype=x.dtype)
    ijob = 1
    info = 0
    ftflag = True
    iter_ = maxiter
    old_ijob = ijob
    first_pass = True
    resid_ready = False
    iter_num = 1
    while True:
        olditer = iter_
        x, iter_, presid, info, ndx1, ndx2, sclr1, sclr2, ijob = \
           revcom(b, x, restrt, work, work2, iter_, presid, info, ndx1, ndx2, ijob, ptol)
        if callback_type == 'x' and iter_ != olditer:
            callback(x)
        slice1 = slice(ndx1-1, ndx1-1+n)
        slice2 = slice(ndx2-1, ndx2-1+n)
        if (ijob == -1):  # gmres success, update last residual
            if callback_type in ('pr_norm', 'legacy'):
                if resid_ready:
                    callback(presid / bnrm2)
            elif callback_type == 'x':
                callback(x)
            break
        elif (ijob == 1):
            work[slice2] *= sclr2
            work[slice2] += sclr1*matvec(x)
        elif (ijob == 2):
            work[slice1] = psolve(work[slice2])
            if not first_pass and old_ijob == 3:
                resid_ready = True

            first_pass = False
        elif (ijob == 3):
            work[slice2] *= sclr2
            work[slice2] += sclr1*matvec(work[slice1])
            if resid_ready:
                if callback_type in ('pr_norm', 'legacy'):
                    callback(presid / bnrm2)
                resid_ready = False
                iter_num = iter_num+1

        elif (ijob == 4):
            if ftflag:
                info = -1
                ftflag = False
            resid, info = _stoptest(work[slice1], atol)

            # Inner loop tolerance control
            if info or presid > ptol:
                ptol_max_factor = min(1.0, 1.5 * ptol_max_factor)
            else:
                # Inner loop tolerance OK, but outer loop not.
                ptol_max_factor = max(1e-16, 0.25 * ptol_max_factor)

            if resid != 0:
                ptol = presid * min(ptol_max_factor, atol / resid)
            else:
                ptol = presid * ptol_max_factor

        old_ijob = ijob
        ijob = 2

        if callback_type == 'legacy':
            # Legacy behavior
            if iter_num > maxiter:
                info = maxiter
                break

    if info >= 0 and not (resid <= atol):
        # info isn't set appropriately otherwise
        info = maxiter
        
    return postprocess(x), info


#======================
#   QMR (Original)
#======================
@non_reentrant()
def qmr(A, b, x0=None, tol=1e-5, maxiter=None, M1=None, M2=None, callback=None,
        atol=None):
    """Use Quasi-Minimal Residual iteration to solve ``Ax = b``.

    Parameters
    ----------
    A : {sparse matrix, dense matrix, LinearOperator}
        The real-valued N-by-N matrix of the linear system.
        Alternatively, ``A`` can be a linear operator which can
        produce ``Ax`` and ``A^T x`` using, e.g.,
        ``scipy.sparse.linalg.LinearOperator``.
    b : {array, matrix}
        Right hand side of the linear system. Has shape (N,) or (N,1).

    Returns
    -------
    x : {array, matrix}
        The converged solution.
    info : integer
        Provides convergence information:
            0  : successful exit
            >0 : convergence to tolerance not achieved, number of iterations
            <0 : illegal input or breakdown

    Other Parameters
    ----------------
    x0  : {array, matrix}
        Starting guess for the solution.
    tol, atol : float, optional
        Tolerances for convergence, ``norm(residual) <= max(tol*norm(b), atol)``.
        The default for ``atol`` is ``'legacy'``, which emulates
        a different legacy behavior.

        .. warning::

           The default value for `atol` will be changed in a future release.
           For future compatibility, specify `atol` explicitly.
    maxiter : integer
        Maximum number of iterations.  Iteration will stop after maxiter
        steps even if the specified tolerance has not been achieved.
    M1 : {sparse matrix, dense matrix, LinearOperator}
        Left preconditioner for A.
    M2 : {sparse matrix, dense matrix, LinearOperator}
        Right preconditioner for A. Used together with the left
        preconditioner M1.  The matrix M1*A*M2 should have better
        conditioned than A alone.
    callback : function
        User-supplied function to call after each iteration.  It is called
        as callback(xk), where xk is the current solution vector.

    See Also
    --------
    LinearOperator

    Examples
    --------
    >>> from scipy.sparse import csc_matrix
    >>> from scipy.sparse.linalg import qmr
    >>> A = csc_matrix([[3, 2, 0], [1, -1, 0], [0, 5, 1]], dtype=float)
    >>> b = np.array([2, 4, -1], dtype=float)
    >>> x, exitCode = qmr(A, b)
    >>> print(exitCode)            # 0 indicates successful convergence
    0
    >>> np.allclose(A.dot(x), b)
    True
    """

    A_ = A
    A, M, x, b, postprocess = make_system(A, None, x0, b)

    if M1 is None and M2 is None:
        if hasattr(A_,'psolve'):
            def left_psolve(b):
                return A_.psolve(b,'left')

            def right_psolve(b):
                return A_.psolve(b,'right')

            def left_rpsolve(b):
                return A_.rpsolve(b,'left')

            def right_rpsolve(b):
                return A_.rpsolve(b,'right')
            M1 = LinearOperator(A.shape, matvec=left_psolve, rmatvec=left_rpsolve)
            M2 = LinearOperator(A.shape, matvec=right_psolve, rmatvec=right_rpsolve)
        else:
            def id(b):
                return b
            M1 = LinearOperator(A.shape, matvec=id, rmatvec=id)
            M2 = LinearOperator(A.shape, matvec=id, rmatvec=id)

    n = len(b)
    if maxiter is None:
        maxiter = n*10

    ltr = _type_conv[x.dtype.char]
    revcom = getattr(_iterative, ltr + 'qmrrevcom')

    get_residual = lambda: np.linalg.norm(A.matvec(x) - b)
    atol = _get_atol(tol, atol, np.linalg.norm(b), get_residual, 'qmr')
    if atol == 'exit':
        return postprocess(x), 0

    resid = atol
    ndx1 = 1
    ndx2 = -1
    # Use _aligned_zeros to work around a f2py bug in Numpy 1.9.1
    work = _aligned_zeros(11*n,x.dtype)
    ijob = 1
    info = 0
    ftflag = True
    iter_ = maxiter
    while True:
        olditer = iter_
        x, iter_, resid, info, ndx1, ndx2, sclr1, sclr2, ijob = \
            revcom(b, x, work, iter_, resid, info, ndx1, ndx2, ijob)
        if callback is not None and iter_ > olditer:
            callback(x)
        slice1 = slice(ndx1-1, ndx1-1+n)
        slice2 = slice(ndx2-1, ndx2-1+n)
        if (ijob == -1):
            if callback is not None:
                callback(x)
            break
        elif (ijob == 1):
            work[slice2] *= sclr2
            work[slice2] += sclr1*A.matvec(work[slice1])
        elif (ijob == 2):
            work[slice2] *= sclr2
            work[slice2] += sclr1*A.rmatvec(work[slice1])
        elif (ijob == 3):
            work[slice1] = M1.matvec(work[slice2])
        elif (ijob == 4):
            work[slice1] = M2.matvec(work[slice2])
        elif (ijob == 5):
            work[slice1] = M1.rmatvec(work[slice2])
        elif (ijob == 6):
            work[slice1] = M2.rmatvec(work[slice2])
        elif (ijob == 7):
            work[slice2] *= sclr2
            work[slice2] += sclr1*A.matvec(x)
        elif (ijob == 8):
            if ftflag:
                info = -1
                ftflag = False
            resid, info = _stoptest(work[slice1], atol)
        ijob = 2

    if info > 0 and iter_ == maxiter and not (resid <= atol):
        # info isn't set appropriately otherwise
        info = iter_

    return postprocess(x), info


#======================
#   CGNE
#======================
@set_docstring('Use Conjugate Gradient Normal Error iteration to solve '
               '``Ax = b``.',
               'The real or complex N-by-N matrix of the linear system.\n'
               'Alternatively, ``A`` can be a linear operator which can\n'
               'produce ``Ax`` using, e.g.,\n'
               '``scipy.sparse.linalg.LinearOperator``.')
@non_reentrant()
def cgne(A, b, x0=None, tol=1e-5, maxiter=None, M=None, callback=None):
    """
    References
    ----------
    [1] Yousef Saad, Iterative Methods for Sparse Linear Systems, Second Edition, SIAM, 2003
    [2] H.Elman, Iterative methods for large, sparse, nonsymmetric systems of linear equations, R        esearch Report 229, Yale University (1982)
    """
    if not (A.shape[0] == A.shape[1] and A.shape[0] == len(b)):
        raise ValueError("The size of the matrix and the right-hand side does not match.")
    if maxiter is None:
        maxiter = 10000
    # type judgment and conversion
    dtype = A.dtype
    if dtype == int:
        dtype = float
        A = A.astype(dtype)
        if b.dtype == int:
            b = b.astype(dtype)
    A, M, x, b, postprocess = make_system(A, M, x0, b)
    # judge if b is a zero vector
    if np.linalg.norm(b) == 0.:
        x = b.copy()
        return (postprocess(x), 0)
    r = b - A.matvec(x)
    At = A.H
    z = M.matvec(r)
    p = At.matvec(z)
    ztr_old = np.inner(z.conjugate(), r)
    r0norm = np.linalg.norm(r)
    if r0norm == 0.:
        return (postprocess(x), 0)
    for iter in range(maxiter):
        w = A.matvec(p)
        alpha = ztr_old / np.inner(p.conjugate(), p)
        x += alpha * p
        r -= alpha * w
        alpha = np.linalg.norm(r) / r0norm
        if callback is not None:
            callback(x)
        if alpha < tol:
            return (postprocess(x), 0)
        elif iter == maxiter - 1:
            return (postprocess(x), maxiter)
        z = M.matvec(r)
        ztr = np.inner(z.conjugate(), r)
        beta = ztr / ztr_old
        p = At.matvec(z) + beta * p
        ztr_old = ztr


#======================
#   CGNR
#======================
@set_docstring('Use Conjugate Gradient Normal Residual iteration to solve '
               '``Ax = b``.',
               'The real or complex N-by-N matrix of the linear system.\n'
               'Alternatively, ``A`` can be a linear operator which can\n'
               'produce ``Ax`` using, e.g.,\n'
               '``scipy.sparse.linalg.LinearOperator``.')
@non_reentrant()
def cgnr(A, b, x0=None, tol=1e-5, maxiter=None, M=None, callback=None):
    """
    References
    ----------
    [1] Yousef Saad, Iterative Methods for Sparse Linear Systems, Second Edition, SIAM, 2003
    [2] H.Elman, Iterative methods for large, sparse, nonsymmetric systems of linear equations, R        esearch Report 229, Yale University (1982)
    """
    if not (A.shape[0] == A.shape[1] and A.shape[0] == len(b)):
        raise ValueError("The size of the matrix and the right-hand side does not match.")
    if maxiter is None:
        maxiter = 10000
    # type judgment and conversion
    dtype = A.dtype
    if dtype == int:
        dtype = float
        A = A.astype(dtype)
        if b.dtype == int:
            b = b.astype(dtype)
    A, M, x, b, postprocess = make_system(A, M, x0, b)
    # judge if b is a zero vector
    if np.linalg.norm(b) == 0.:
        x = b.copy()
        return (postprocess(x), 0)
    r = b - A.matvec(x)
    At = A.H
    rhat = At.matvec(r)
    z = M.matvec(rhat)
    p = z.copy()
    ztrhat_old = np.inner(z.conjugate(), rhat)
    r0norm = np.linalg.norm(r)
    if r0norm == 0.:
        return (postprocess(x), 0)
    for iter in range(maxiter):
        w = A.matvec(p)
        alpha = ztrhat_old / np.inner(w.conjugate(), w)
        x += alpha * p
        r -= alpha * w
        alpha = np.linalg.norm(r) / r0norm
        if callback is not None:
            callback(x)
        if alpha < tol:
            return (postprocess(x), 0)
        elif iter == maxiter - 1:
            return (postprocess(x), maxiter)
        rhat = At.matvec(r)
        z = M.matvec(rhat)
        ztrhat = np.inner(z.conjugate(), rhat)
        beta = ztrhat / ztrhat_old
        p = z + beta * p
        ztrhat_old = ztrhat


#======================
#   Improved CGS
#======================
@set_docstring('Use Improved Conjugate Gradient Squared iteration to solve ``Ax = b``.',
               'The real-valued N-by-N matrix of the linear system.\n'
               'Alternatively, ``A`` can be a linear operator which can\n'
               'produce ``Ax`` using, e.g.,\n'
               '``scipy.sparse.linalg.LinearOperator``.')
@non_reentrant()
def icgs(A, b, x0=None, tol=1e-5, maxiter=None, M=None, callback=None):
    if not (A.shape[0] == A.shape[1] and A.shape[0] == len(b)):
        raise ValueError("The size of the matrix and the right-hand side does not match.")
    if maxiter is None:
        maxiter = 10000
    # type judgment and conversion
    dtype = A.dtype
    if dtype == int:
        dtype = float
        A = A.astype(dtype)
        if b.dtype == int:
            b = b.astype(dtype)
    A, M, x, b, postprocess = make_system(A, M, x0, b)
    # judge if b is a zero vector
    if np.linalg.norm(b) == 0.:
        x = b.copy()
        return (postprocess(x), 0)
    r = b - A.matvec(x)
    # why not set rhat = M.matvec(r) directly ?
    tmp = r.copy()
    rhat = M.matvec(tmp)
    z = rhat.copy()
    d_old = np.inner(rhat.conjugate(), z)
    p = r.copy()
    q = r.copy()
    beta = 0.
    r0norm = np.linalg.norm(r)
    if r0norm == 0.:
        return (postprocess(x), 0)
    for iter in range(maxiter):
        w = z + beta * q
        p = w + beta * q + (beta**2) * p
        Ap = A.matvec(p)
        z = M.matvec(Ap)
        d = np.inner(rhat.conjugate(), z)
        if d == 0.:
            return (postprocess(x), -1)
        alpha = d_old / d
        q = w - alpha * z
        w += q
        x += alpha * w
        r -= alpha * A.matvec(w)
        alpha = np.linalg.norm(r) / r0norm
        if callback is not None:
            callback(x)
        if alpha < tol:
            return (postprocess(x), 0)
        elif iter == maxiter - 1:
            return (postprocess(x), maxiter)
        z = M.matvec(r)
        d = np.inner(rhat.conjugate(), z)
        if d == 0.:
            return (postprocess(x), -1)
        beta = d / d_old
        d_old = d
