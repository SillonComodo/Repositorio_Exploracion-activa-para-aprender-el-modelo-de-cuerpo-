"""
adaptive_linear_interest.py
============================
Explauto interest model based on linear regression over an adaptive-size
competence buffer.

Algorithm
---------
At each update step:
  1. Compute competence  c = competence_dist(target, reached)
  2. Append c to a circular buffer of size  win_size
  3. Fit a degree-1 polynomial (line) over  (t_0, c_0), ..., (t_n, c_n)
     where t_i is the index inside the buffer.
  4. The slope of that line is the *interest*.
  5. Adapt the buffer size:
       slope > 0  (competence improving)  =>  win_size += step_increase  (up to win_max)
       slope < 0  (competence worsening)  =>  win_size -= step_decrease  (down to win_min)

Sampling
--------
  * With probability eps_random  : sample uniformly in the exploration space.
  * Otherwise                    : sample near the stored motor command with
                                   the highest competence in the recent window,
                                   with small Gaussian perturbation.

Note on sign convention with competence_dist
---------------------------------------------
competence_dist returns  -||target - reached||, which is always <= 0.
Closer to 0 means better performance.
  * Positive slope  =>  competence is rising  =>  robot is improving
  * Negative slope  =>  competence is falling =>  robot is worsening

This matches the intended adaptive rule: grow the buffer while improving,
shrink it when performance degrades.
"""
from __future__ import print_function

import numpy
from collections import deque

from .interest_model import InterestModel
from .competences import competence_dist
from ..utils import rand_bounds


class AdaptiveLinearInterest(InterestModel):
    """
    Interest model that uses the slope of a linear regression over an
    adaptive competence buffer as the interest signal.

    Parameters
    ----------
    conf : explauto configuration object
    expl_dims : list of int
        Dimensions of the exploration space (typically motor space for MBIM).
    win_size_init : int
        Initial size of the competence buffer.
    win_min : int
        Minimum allowed buffer size.
    win_max : int
        Maximum allowed buffer size.
    step_decrease : int
        Amount by which the buffer shrinks when slope < 0.
    step_increase : int
        Amount by which the buffer grows when slope > 0.
    eps_random : float in [0, 1]
        Probability of sampling uniformly at random instead of
        exploiting high-competence regions.
    competence_measure : callable
        Function (xy, ms) -> float measuring the competence.
        Defaults to competence_dist.
    """

    def __init__(self,
                 conf,
                 expl_dims,
                 win_size_init=50,
                 win_min=20,
                 win_max=100,
                 step_decrease=1,
                 step_increase=2,
                 eps_random=0.05,
                 competence_measure=competence_dist):

        InterestModel.__init__(self, expl_dims)

        self.bounds = conf.bounds[:, expl_dims]
        self.competence_measure = competence_measure

        # --- Buffer parameters ---
        self.win_min = max(2, win_min)      # need at least 2 points to fit a line
        self.win_max = win_max
        self.step_decrease = step_decrease
        self.step_increase = step_increase
        self.eps_random = eps_random

        # --- Current buffer ---
        self.win_size = max(self.win_min, min(self.win_max, win_size_init))
        self.buffer_c = deque(maxlen=self.win_size)

        # --- Full history for sampling ---
        # Stores all observed (motor_position, competence) pairs
        self.all_x = []   # list of numpy arrays in expl_dims space
        self.all_c = []   # list of float competence values

        # --- Diagnostics ---
        self.current_slope = 0.0
        self.current_interest = 0.0

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resize_buffer(self, new_size):
        """Change the buffer capacity while preserving the most recent data."""
        new_size = int(max(self.win_min, min(self.win_max, new_size)))
        if new_size != self.win_size:
            # Keep the most recent `new_size` competence values
            recent = list(self.buffer_c)[-new_size:]
            self.win_size = new_size
            self.buffer_c = deque(recent, maxlen=self.win_size)

    def _compute_slope(self):
        """
        Fit a line to the buffered competence values and return the slope.

        Returns 0.0 when fewer than 2 samples are available.
        """
        n = len(self.buffer_c)
        if n < 2:
            return 0.0
        t = numpy.arange(n, dtype=numpy.float64)
        c = numpy.array(list(self.buffer_c), dtype=numpy.float64)
        # numpy.polyfit returns [slope, intercept] for degree 1
        try:
            coeffs = numpy.polyfit(t, c, 1)
            slope = coeffs[0]
        except numpy.linalg.LinAlgError:
            slope = 0.0
        # Guard against NaN / Inf
        if not numpy.isfinite(slope):
            slope = 0.0
        return slope

    # ------------------------------------------------------------------
    # InterestModel interface
    # ------------------------------------------------------------------

    def update(self, xy, ms):
        """
        Update the interest model with a new (command, outcome) pair.

        Parameters
        ----------
        xy : array-like
            Full state vector including motor command (at expl_dims).
        ms : array-like
            Achieved sensory state update(same indexing as xy).

        Returns
        -------
        slope : float
            Current interest (slope of the linear regression).
        """
        # 1. Compute competence
        c = self.competence_measure(xy, ms)
        x = numpy.asarray(xy)[self.expl_dims].copy()

        # 2. Append to buffer and full history
        self.buffer_c.append(c)
        self.all_x.append(x)
        self.all_c.append(c)

        # 3. Compute slope (interest)
        slope = self._compute_slope()
        self.current_slope = slope
        self.current_interest = abs(slope)

        # 4. Adapt buffer size
        if slope > 0:
            # Competence is improving -> expand memory
            self._resize_buffer(self.win_size + self.step_increase)
        elif slope < 0:
            # Competence is worsening -> focus on recent dynamics
            self._resize_buffer(self.win_size - self.step_decrease)
        # slope == 0: no change

        # Print diagnostics
        print('[ALIM] slope={:.4f}  interest={:.4f}  win_size={}'.format(
            self.current_slope, self.current_interest, self.win_size))

        return slope

    def sample(self):
        """
        Sample a point in the exploration space (motor space for MBIM).

        Strategy
        --------
        - Random  (prob = eps_random): uniform draw within bounds.
        - Greedy  (prob = 1 - eps_random): sample near the motor command
          from the most recent window that had the best competence, with
          small Gaussian perturbation to encourage local exploration.
        """
        if len(self.all_x) == 0 or numpy.random.random() < self.eps_random:
            return rand_bounds(self.bounds).flatten()

        # --- Build weighted sample from recent history ---
        n_recent = min(len(self.all_x), self.win_size)
        recent_x = self.all_x[-n_recent:]
        recent_c = numpy.array(self.all_c[-n_recent:], dtype=numpy.float64)

        # Shift so all weights are positive; higher competence = higher weight
        c_shifted = recent_c - recent_c.min() + 1e-8
        weights = c_shifted / c_shifted.sum()

        # Weighted random pick of a past motor command
        idx = numpy.random.choice(len(recent_x), p=weights)
        center = recent_x[idx].copy()

        # Small Gaussian perturbation proportional to the range of each dim
        sigma = 0.05 * (self.bounds[1] - self.bounds[0])
        sample = center + numpy.random.randn(len(center)) * sigma

        # Clip to bounds
        sample = numpy.maximum(sample, self.bounds[0])
        sample = numpy.minimum(sample, self.bounds[1])
        return sample

    # ------------------------------------------------------------------
    # Diagnostic accessors
    # ------------------------------------------------------------------

    def slope(self):
        """Return current interest slope."""
        return self.current_slope

    def interest(self):
        """Return current interest magnitude (|slope|)."""
        return self.current_interest

    def current_win_size(self):
        """Return current buffer size."""
        return self.win_size

    def n_points(self):
        """Return the total number of observations received so far."""
        return len(self.all_x)


# ---------------------------------------------------------------------------
# Registration for explauto's from_configuration factory
# ---------------------------------------------------------------------------
interest_models = {
    'adaptive_linear': (
        AdaptiveLinearInterest,
        {
            'default': {
                'win_size_init': 50,
                'win_min':        20,
                'win_max':       100,
                'step_decrease':  1,
                'step_increase':  2,
                'eps_random':    0.05,
                'competence_measure': competence_dist,
            }
        }
    )
}
