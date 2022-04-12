from typing import List, Optional, Tuple

import numpy as np

from ...quadrature.interfaces.standard_kernels import IProductMatern32
from ...quadrature.kernels.integration_measures import IntegrationMeasure
from .quadrature_kernels import QuadratureKernel


class QuadratureMatern32(QuadratureKernel):
    """Augments a ProductMatern32 kernel with integrability."""

    def __init__(
        self,
        matern_kernel: IProductMatern32,
        integral_bounds: Optional[List[Tuple[float, float]]],
        measure: Optional[IntegrationMeasure],
        variable_names: str = "",
    ) -> None:
        """
        :param matern_kernel: Standard emukit matern32-kernel.
        :param integral_bounds: Defines the domain of the integral. List of D tuples, where D is the dimensionality
        of the integral and the tuples contain the lower and upper bounds of the integral.
        i.e., [(lb_1, ub_1), (lb_2, ub_2), ..., (lb_D, ub_D)]. None for infinite bounds
        :param measure: An integration measure. None means the standard Lebesgue measure is used.
        :param variable_names: The (variable) name(s) of the integral
        """

        super().__init__(
            kern=matern_kernel, integral_bounds=integral_bounds, measure=measure, variable_names=variable_names
        )

    @property
    def lengthscales(self):
        return self.kern.lengthscales

    @property
    def variance(self):
        return self.kern.variance

    def qK(self, x2: np.ndarray) -> np.ndarray:
        """ProductMatern32 kernel with the first component integrated out aka kernel mean

        :param x2: remaining argument of the once integrated kernel, shape (n_point N, input_dim)
        :returns: kernel mean at location x2, shape (1, N)
        """
        raise NotImplementedError

    def Kq(self, x1: np.ndarray) -> np.ndarray:
        """ProductMatern32 kernel with the second component integrated out aka kernel mean

        :param x1: remaining argument of the once integrated kernel, shape (n_point N, input_dim)
        :returns: kernel mean at location x1, shape (N, 1)
        """
        return self.qK(x1).T

    def qKq(self) -> float:
        """ProductMatern32 kernel integrated over both arguments x1 and x2.

        :returns: double integrated kernel
        """
        raise NotImplementedError

    def dqK_dx(self, x2: np.ndarray) -> np.ndarray:
        """
        gradient of the kernel mean (integrated in first argument) evaluated at x2
        :param x2: points at which to evaluate, shape (n_point N, input_dim)
        :return: the gradient with shape (input_dim, N)
        """
        raise NotImplementedError

    def dKq_dx(self, x1: np.ndarray) -> np.ndarray:
        """
        gradient of the kernel mean (integrated in second argument) evaluated at x1
        :param x1: points at which to evaluate, shape (n_point N, input_dim)
        :return: the gradient with shape (N, input_dim)
        """
        return self.dqK_dx(x1).T


class QuadratureProductMatern32LebesgueMeasure(QuadratureMatern32):
    """A Matern32 product kernel with integrability over the standard Lebesgue measure.

    Can only be used with finite integral bounds.
    """

    def __init__(
        self, matern_kernel: IProductMatern32, integral_bounds: List[Tuple[float, float]], variable_names: str = ""
    ) -> None:
        """
        :param matern_kernel: Standard emukit matern32-kernel.
        :param integral_bounds: defines the domain of the integral. List of D tuples, where D is the dimensionality
        of the integral and the tuples contain the lower and upper bounds of the integral
        i.e., [(lb_1, ub_1), (lb_2, ub_2), ..., (lb_D, ub_D)].
        :param variable_names: The (variable) name(s) of the integral.
        """
        super().__init__(
            matern_kernel=matern_kernel, integral_bounds=integral_bounds, measure=None, variable_names=variable_names
        )

    def qK(self, x2: np.ndarray, skip: List[int] = None) -> np.ndarray:
        """Matern32 prodct kernel with the first component integrated out aka kernel mean.

        :param x2: remaining argument of the once integrated kernel, shape (n_point N, input_dim)
        :param skip: Skip those dimensions from product.
        :returns: kernel mean at location x2, shape (1, N)
        """
        if skip is None:
            skip = []

        qK = np.ones(x2.shape[0])
        for dim in range(x2.shape[1]):
            if dim in skip:
                continue
            qK *= self._qK_1d(x=x2[:, dim], domain=self.integral_bounds.bounds[dim], ell=self.lengthscales[dim])
        return qK[None, :] * self.variance

    def qKq(self) -> float:
        """Matern32 kernel integrated over both arguments x1 and x2

        :returns: double integrated kernel
        """
        qKq = 1.0
        for dim in range(self.input_dim):
            qKq *= self._qKq_1d(domain=self.integral_bounds.bounds[dim], ell=self.lengthscales[dim])
        return self.variance * qKq

    def dqK_dx(self, x2: np.ndarray) -> np.ndarray:
        """
        gradient of the kernel mean (integrated in first argument) evaluated at x2
        :param x2: points at which to evaluate, shape (n_point N, input_dim)
        :return: the gradient with shape (input_dim, N)
        """

        input_dim = x2.shape[1]
        dqK_dx = np.zeros([input_dim, x2.shape[0]])
        for dim in range(input_dim):
            grad_term = self._dqK_dx_1d(
                x=x2[:, dim], domain=self.integral_bounds.bounds[dim], ell=self.lengthscales[dim]
            )
            dqK_dx[dim, :] = grad_term * self.qK(x2, skip=[dim])[0, :]
        return dqK_dx

    # one dimensional integrals start here
    def _qK_1d(self, x: np.ndarray, domain: Tuple[float, float], ell: float) -> np.ndarray:
        """Unscaled kernel mean for 1D Matern kernel."""
        (a, b) = domain
        s3 = np.sqrt(3.0)
        first_term = 4.0 * ell / s3
        second_term = -np.exp(s3 * (x - b) / ell) * (b + 2.0 * ell / s3 - x)
        third_term = -np.exp(s3 * (a - x) / ell) * (x + 2.0 * ell / s3 - a)
        return first_term + second_term + third_term

    def _qKq_1d(self, domain: Tuple[float, float], ell: float) -> float:
        """Unscaled kernel variance for 1D Matern kernel."""
        a, b = domain
        r = b - a
        c = np.sqrt(3.0) * r
        qKq = 2.0 * ell / 3.0 * (2.0 * c - 3.0 * ell + np.exp(-c / ell) * (c + 3.0 * ell))
        return float(qKq)

    def _dqK_dx_1d(self, x, domain, ell):
        """Unscaled gradient of 1D Matern kernel mean."""
        s3 = np.sqrt(3)
        a, b = domain
        exp_term_b = np.exp(s3 * (x - b) / ell)
        exp_term_a = np.exp(s3 * (a - x) / ell)
        first_term = exp_term_b * (-1 + (s3 / ell) * (x - b))
        second_term = exp_term_a * (+1 - (s3 / ell) * (a - x))
        return first_term + second_term