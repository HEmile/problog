import torch
import pyro
import math

from .algebra import Algebra, BaseS, SUB

str2distribution = {
    "delta": pyro.distributions.Delta,
    "normal": pyro.distributions.Normal,
    "normalMV": pyro.distributions.MultivariateNormal,
    "uniform": pyro.distributions.Uniform,
    "beta": pyro.distributions.Beta,
    "poisson": pyro.distributions.Poisson,
}


class MixtureComponent(object):
    def __init__(self, samples, weights, component_index):
        self.samples = samples
        self.weights = weights
        self.component_index = component_index

    def __truediv__(self, other):
        return MixtureComponent(
            self.samples, self.weights / other, self.component_index
        )

    def __str__(self):
        return "MixComp{}".format(str(self.component_index).translate(SUB))


class S(BaseS):
    def __init__(self, tensor, variables=set()):
        BaseS.__init__(self, tensor, variables)

    def __add__(self, other):
        return S(self.value + other.value, variables=self.variables | other.variables)

    def __sub__(self, other):
        return S(self.value - other.value, variables=self.variables | other.variables)

    def __mul__(self, other):
        return S(self.value * other.value, variables=self.variables | other.variables)

    def __truediv__(self, other):
        return S(self.value / other.value, variables=self.variables | other.variables)

    def __pow__(self, other):
        return S(self.value ** other.value, variables=self.variables | other.variables)

    def exp(self):
        if isinstance(self, (int, float)):
            return math.exp(self)
        else:
            return S(torch.exp(self.value), variables=self.variables)

    def sigmoid(self):
        if isinstance(self, (int, float)):
            return 1.0 / (1 + math.exp(-self))
        else:
            return S(torch.sigmoid(self.value), variables=self.variables)

    # TODO rewrite this with >= instead of max stuff?
    @staticmethod
    def gtz(a):
        if isinstance(a, (int, float)):
            return max(a, 0) / a
        else:
            z = torch.zeros((1,))
            a = torch.abs(torch.max(a, z) / a)
            return a

    def lt(self, other):
        value = other.value - self.value
        value = self.gtz(value)
        return S(value, variables=self.variables | other.variables)

    def le(self, other):
        value = other.value - self.value
        value = self.gtz(value)
        s = S(value, variables=self.variables | other.variables)
        return s

    def gt(self, other):
        value = self.value - other.value
        value = self.gtz(value)
        s = S(value, variables=self.variables | other.variables)
        return s

    def ge(self, other):
        value = self.value - other.value
        value = self.gtz(value)
        s = S(value, variables=self.variables | other.variables)
        return s

    def eq(self, other):
        raise NotImplementedError()

    def ne(self, other):
        raise NotImplementedError()

    def obs(self, other):
        value = other.value
        s = S(value, variables=self.variables | other.variables)

        import sys

        sys.exit()
        return s


class Pyro(Algebra):
    def __init__(self, values, n_samples, ttype, device):
        Algebra.__init__(self, values)
        self.Tensor = self.setup_tensor(ttype, device)
        torch.set_default_tensor_type(self.Tensor)

        self.n_samples = n_samples
        self.device = torch.device(device)

    def setup_tensor(self, ttype, device):
        if ttype == "float64" and device == "cpu":
            Tensor = torch.DoubleTensor
        elif ttype == "float32" and device == "cpu":
            Tensor = torch.FloatTensor
        elif ttype == "float64":
            Tensor = torch.cuda.DoubleTensor
        elif ttype == "float32":
            Tensor = torch.cuda.FloatTensor
        return Tensor

    def symbolize(self, expression, variables=set()):
        if isinstance(expression, (int, float)):
            return S(float(expression))
        else:
            return S(expression, variables=set(variables))

    def integrate(self, weight, free_variable=None, normalization=False):
        if free_variable:
            self.create_values(free_variable)
            values = self.random_values[free_variable]
            print(values)
            # TODO pass on variables
            return S(MixtureComponent(values, weight.value, free_variable[1]))
        else:
            if isinstance(weight.value, (int, float)):
                return S(weight.value)
            else:
                return S(torch.mean(weight.value))

    @staticmethod
    def _format_density(density, dim, n_samples):
        if tuple(density.batch_shape) == (dim, n_samples):
            return density
        elif tuple(density.batch_shape) == (n_samples,):
            return density.expand_by(torch.Size((dim,)))
        else:
            return density.expand_by(torch.Size((dim, n_samples)))

    def construct_density(self, name, dim, functor, args):
        args = [a.value for a in args]
        if functor in (
            pyro.distributions.Delta,
            pyro.distributions.Normal,
            pyro.distributions.Uniform,
            pyro.distributions.Beta,
            pyro.distributions.Poisson,
        ):
            # return functor(*args)
            density = functor(*args)
            return self._format_density(density, dim, self.n_samples)
        # elif functor in (torch.normalInd_pdf,):
        #     return functor(*args)

    def make_values(self, name, components, functor, args):
        if name in self.random_values:
            pass
        else:
            functor = str2distribution[functor]
            density = self.construct_density(name, len(components), functor, args)
            samples = pyro.sample(name, density)
            self.densities[name] = density
            self.random_values[name] = samples

    def construct_negated_algebraic_expression(self, symbol):
        n_symbol = 1.0 - symbol.value
        return self.symbolize(n_symbol, symbol.variables)

    def make_observation(self, var, obs):
        density_name = var.name
        dimensions = var.dimensions
        assert dimensions == 1  # TODO allow for multivariate observations

        for c in var.components:
            self.construct_algebraic_expression(c)
        obs = self.construct_algebraic_expression(obs)
        density = self.densities[density_name]
        observation_weight = torch.exp(density.log_prob(torch.tensor(obs.value)))

        self.random_values[density_name][dimensions - 1] = obs.value
        # this is the line that relates to the comment above

        return observation_weight
