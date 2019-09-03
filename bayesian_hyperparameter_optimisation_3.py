#!/usr/bin/python
# -*- coding: iso-8859-15 -*-


# --------------------------
# Bayesian Optimisation Code
# --------------------------

from scipy.stats import norm
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, RBF
from scipy.optimize import minimize
from pyDOE import *
from sklearn.model_selection import cross_val_score
import matplotlib.pyplot as plt
from matplotlib import rcParams


import logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# -----------------------------------------
# --- Class for a continuous hyperparameter
# -----------------------------------------

class hyperparam(object):
    """
    Define a hyperparameter class that contains all the required specs of the hyperparameter
    --- Param ---
    list_in : list
        The length of the list will define the hyperparameter kind.
        len(list_in) == 2 : assume hyperparameter is continuous and the list defines the lower and upper bound
        len(list_in) > 2 : assume the hyperparameter is discrete and can only take the specified values
    --- Attributes ---
    bounds : [lower_bound, upper_bound]
        bounds for the values of the jhyperparameter
    kind : str
        continuous or discrete
    vals [discrete only] : list
        list of all possible values of the hyper parameter
    """

    def __init__(self, list_in):

        # Initiate with 2 types of variable. We either specify bounds
        # for continuous variable or values for discrete. Note that for
        # now the values must be integers and be a list of consecutive
        #  integers.
        if len(list_in) == 2:
            self.bounds = list_in
            self.kind = 'continuous'
        elif len(list_in) > 2:
            self.bounds = [list_in[0], list_in[-1]]
            self.kind = 'discrete'
            self.vals = list_in


class iteration(object):
    """
    Class to carry out a single iteration of the optimisation by finding the maximum in the acquisition function

    --- Params ---
    pars : class
        instance of the main Bayesian optimisation class to pass in information from previous iterations

    --- Attributes ---
    Xt : array ({number samples taken so far} x {number of hyperparameters})
        array of sampled hyperparameter values so far
    Yt : array ({number samples taken so far}, )
        accuracy of model calculated from the statistical emulator
    gpr :
        Train Gaussian Process on sampled points
    N_hps : int
        number of hyperparameters
    X_nextdict : dict
        keys - name of hyperparameter
        values - sampled points so far

    --- Methods ---
    propose_location :
        Proposes the next sampling point by optimizing the acquisition function.
    min_obj :
        function we want to minimise; this is -expected_improvement so that when we take calculate the minimum we are
        actually finding the maximum of the acquisition function
    expected_improvement :
        Calculates the expected improvement (acquisition function) for a given set of hyperparameter values

    """

    def __init__(self, pars):

        # --- Sample data
        self.Xt = pars.Xt
        self.Yt = pars.Yt
        self.pars = pars

        # Obtain next sampling point from the acquisition function (expected_improvement)
        X_next = self.propose_location(pars)
        # Convert to int where necessary
        
        # We need to recreate a dictionary with the keys given by the hyperparameter name before passing into our
        # MLmodel
        self.X_nextdict = {}
        for i, hps1 in enumerate(sorted(pars.Xtdict.keys())):
            if pars.hps[hps1].kind == 'discrete':
                X_next[i] = int(X_next[i])
                self.X_nextdict[hps1] = X_next[i]
            else:
                self.X_nextdict[hps1] = X_next[i]

        # X_next = np.array(X_next,ndmin=(2)).reshape(1,-1)
        Y_next = pars.objF(self.X_nextdict)

        # Add the new sample point to the existing for the next iteration
        self.Xt = np.vstack((self.Xt, X_next.reshape(1, -1)[0]))
        self.Yt = np.concatenate((self.Yt, Y_next))

    # Sampling function to find the next values for the hyperparameters
    def propose_location(self, pars):
        """
        Proposes the next sampling point by optimizing the acquisition function.
        --- params ---
        Args : acquisition: Acquisition function.
        X_sample : Sample locations (n x d).
        Y_sample : Sample values (n x 1).
        gprc: A GaussianProcessRegressor fitted to samples.
        
        --- Returns ---
        Location of the acquisition function maximum.
        """
        
        self.N_hps = pars.Xt.shape[1]
        min_val = 1
        min_x = None

        self.gpr = pars.gpr
        self.Xt = pars.Xt

        # Find the best optimum by starting from n_restart different random points.
        Xs = lhs(self.N_hps, samples=pars.n_restarts, criterion='centermaximin')
        for i, hp in enumerate(sorted(pars.hps.keys())):

            Xs[:, i] = Xs[:, i] * (pars.hps[hp].bounds[1] - pars.hps[hp].bounds[0]) + pars.hps[hp].bounds[0]

            # Convert int values to integers
            if pars.hps[hp].kind == 'discrete':
                Xs[:, i] = Xs[:, i].astype(int)

        # Find the best optimum by starting from n_restart different random points.
        # Xs = lhs(self.pars.Ncontinuous_hps, samples=pars.n_restarts, criterion='centermaximin')
        # for i, hp in enumerate(sorted(self.pars.continous_hps)):
        #     Xs[:, i] = Xs[:, i] * (pars.hps[hp].bounds[1] - pars.hps[hp].bounds[0]) + \
        #                    pars.hps[hp].bounds[0]

        # # Find the maximum in the acquisition function

        print("next iteration")
        if pars.optim_rout == 'minimize':
            for x0 in Xs:
                res = minimize(self.min_obj, x0=x0, bounds=pars.bounds, method=pars.method)
                # Find the best optimum across all initiations
                if res.fun < min_val:
                    min_val = res.fun[0]
                    min_x = res.x


                    
        # elif pars.optim_rout == 'MCMC-MH':
        #     for x0 in Xs:
        #         res_x,res_f = self.MetroHastings(x0,[0.01]*self.N_hps,1000,tuple(pars.bounds))
        #         if res_f < min_val:
        #             min_val = res_f
        #             min_x = res_x
        #
        # elif pars.optim_rout == 'MCMC-discrete':
        #     for x0 in Xs:
        #         res_x, res_f = self.discrete_MCMC(x0, pars.x_dict, 1000)
        #         if res_f < min_val:
        #             min_val = res_f
        #             min_x = res_x

        return min_x.reshape(-1, 1)

    # def add_discrete_variables(self, x0, ):

    def min_obj(self, X):
        # Minimization objective is the negative acquisition function
        return -self.expected_improvement(X.reshape(-1, self.N_hps))
    
    def max_obj(self, X):
        # Minimization objective is the negative acquisition function
        return self.expected_improvement(X.reshape(-1, self.N_hps))

    # Acquisition function - here we use expected improvement
    def expected_improvement(self, X):

        # --- Computes the EI at points X based on existing samples X_sample and Y_sample using a Gaussian process 
        # surrogate model. 
        # X: Points at which EI shall be computed (m x d). 
        # X_sample: Sample locations (n x d). 
        # Y_sample: Sample values (n x 1). 
        # gpr: A GaussianProcessRegressor fitted to samples. 
        # xi: Exploitation-exploration trade-off parameter. 
        # .   - xi ~ O(0) => exploitation
        # .   - xi ~ O(1) => exploration
        # Returns: Expected improvements at points X.
        for i, hyper_param in enumerate(sorted(self.pars.hps.keys())):
            if self.pars.hps[hyper_param].kind == 'discrete':
                X[:, i] = np.round(X[:, i][0])

        # Evaluate the Gaussian Process at a test location X to get the mean and std
        mu, sigma = self.gpr.predict(X, return_std=True)
        # Evaluate the Gaussian Process at the sampled points - this gets the mean values without the noise
        mu_sample = self.gpr.predict(self.Xt)

        sigma = sigma.reshape(-1, 1)  # self.Xt.shape[1])

        # Needed for noise-based model,
        # otherwise use np.max(Y_sample).
        # See also section 2.4 in [...]
        mu_sample_opt = np.max(mu_sample)

        imp = mu - mu_sample_opt
        Z = imp / sigma

        Ei = (mu - mu_sample_opt) * norm.cdf(mu, loc=mu_sample_opt, scale=sigma) \
             + mu_sample_opt * norm.pdf(mu, loc=mu_sample_opt, scale=sigma)

        return Ei

    
    def MetroHastings(self,x0,sig,Niter,bounds):
    
        "Function to perform metropolis Hastings sampling in an MCMC"

        # --- Input ---
        # x0: initial guess for random walk - list of continuous variables
        # sig is the uncertainty in the MH sampling algorithm
        # Niter is number of iterations to perform
        # bounds: list of tuples of length x0, each one being the lower and upper bounds 

        # --- Output ---
        # Modal solution from the MCMC

        # Calculate initial guess
        acq = np.zeros(Niter)
        acq[0] = self.min_obj(x0.reshape(1,-1))
        
        # proposition point
        xp = np.zeros((len(x0),Niter))
        xp[:,0] = x0

        for iiter in range(1,Niter):
            # Propose new data point to try using MH
            for i in range(len(x0)):

                # iterate until we get a point in the correct interval
                if x0[i]<bounds[i][0]:
                    loc0 = bounds[i][0]
                elif x0[i]>bounds[i][1]:
                    loc0 = bounds[i][1]
                else:
                    loc0 = x0[i]

                Pnext = np.random.normal(loc=loc0,scale=sig[i])
                while (Pnext < bounds[i][0]) | (Pnext >= bounds[i][1]):
                    Pnext = np.random.normal(loc=loc0,scale=sig[i])

                # Then choose the first point that is    
                xp[i,iiter] = Pnext

            # Test value at this point
            acq[iiter] = self.min_obj(xp[:,iiter].reshape(1,-1))

            # Check if proposed point is better
            if acq[iiter] > acq[iiter-1]:
                x0 = xp[:,iiter].copy()

            else:
                if acq[iiter] == 0:
                    x0 = xp[:,iiter-1].copy()
                else:
                    p0 = [acq[iiter-1]/(acq[iiter]+acq[iiter-1]),acq[iiter]/(acq[iiter]+acq[iiter-1])]

                    nextP = np.random.choice([0,1],p=p0)

                    if nextP == 1:
                        x0 = xp[:,iiter].copy()
                    else:
                        x0 = xp[:,iiter-1].copy()
                    
            
        # Now get optimal solution by fitting a histogram to the data - ignore first 10% of samples
        optim_x = np.zeros((1,len(x0)))   
        for i in range(optim_x.shape[1]):
            optim_x[0,i] = self.kernel_density_estimation(xp[i,int(0.1*Niter):],Niter)

        return optim_x,self.min_obj(optim_x.reshape(1,-1))

    def kernel_density_estimation(self,xpi,Niter):

        " Function to find peak in a kernel density "

        # We initially fudge this to get it working! 
        # So we fit a histogram and then find the middle of the tallest bar

        # Fit a histogram
        data = xpi.copy()
        data.sort()
        hist, bin_edges = np.histogram(data, density=True,bins=max(10,30))

        # Return the middle of the largest bin
        n = np.argmax(hist)
        return np.mean(bin_edges[n:n+2])
    
    def discrete_MCMC(self, x0, x_dict, Niter):

        """
        Function to perform fully discrete 'Metropolis Hastings' sampled MCMC

        --- Params ---
        x0 : float
            starting guess
        Niter : int
            number of iterations to perform
        bounds : dict
            dictionary of values for each variable with key equal to the position in the array

        --- Returns ---
        Modal solution from the MCMC
        """

        # Calculate initial guess
        acq = np.zeros(Niter)
        acq[0] = self.min_obj(x0.reshape(1, -1))
        
        
        # proposition point
        xp = np.zeros((len(x0),Niter))
        xp[:,0] = x0

        # count frequency of each value appearing
        N_dict = {}
        for k1 in x_dict.keys():
            N_dict[k1] = np.zeros(len(x_dict[k1]))

        for iiter in range(1,Niter):

            # Choose a location to swap
            i_choice = np.random.choice(range(len(x0)))

            # Set xp to be x0
            xp[:,iiter] = x0.copy()
            # choose a new value for the i_choice-th entry
            xp[i_choice,iiter] = np.random.choice(x_dict[i_choice])

            # Test value at this point
            acq[iiter] = self.min_obj(xp[:,iiter].reshape(1,-1))

            # Check if proposed point is better
            if acq[iiter] > acq[iiter-1]:
                x0 = xp[:,iiter].copy()

            else:

                p0 = [acq[iiter-1]/(acq[iiter]+acq[iiter-1]),acq[iiter]/(acq[iiter]+acq[iiter-1])]
                nextP = np.random.choice([0,1],p=p0)
                if nextP == 1:
                    x0 = xp[:,iiter].copy()
                else:
                    x0 = xp[:,iiter-1].copy()

            # accumulate the counts - when iiter excedes a 10th of Niter
            if iiter > 0.1*Niter:
                for aci in range(len(x0)):
                    N_dict[aci][x_dict[aci].index(x0[aci])] += 1

        # Now get optimal solution by fitting a histogram to the data - already ignored first 10% of samples
        optim_x = np.zeros((1,len(x0)))   
        for i in range(len(x0)):
            optim_x[0,i] = x_dict[i][np.argmax(N_dict[i])]

        return optim_x,self.min_obj(optim_x.reshape(1,-1))
    
    
class BayesianOptimisation(object):
    """
    Main class for the optimisation

    --- Params ---
    hps : dict
        keys - names of hyperparameters. Note this should correspond to the name of the parameter in MLmodel
        values - [upper_bound, lower_bound] for continuous, list (length > 2) for discrete
    MLmodel : ml model instance
        The model you want to optimise
    optim_rout : str
        name of optimisation routine you want to use. For now just use minimize until alternatives for dealing with
        discrete and categorical values can be better implemented; this will be in a later release.
    using_own_score : bool, DEFAULT : False
        If false then use MLmodel.score() to measure performance of the model
    scoring_function : func
        Scoring function to use if using_own_model = False
    NpI : int
        Number of initial samples to train the Gaussian Process emulator on
    Niter : int
        Number of iterations to perform
    n_restarts : int
        Number of times we reinitiate the minimization routine to find the maximum of the acquisition function - avoids
        local maxima
    method : str, DEFAULT: 'L-BFGS-B'
        Optimisation algorithm used by minimize
    kernel : func, DEFAULT: RBF()
        Kernel used in the Gaussian Process
    noise : float
        noise parameter used in the Gaussian Process - measures the uncertainty between the mean of the Gaussian process
        and the data. Very low values means the mean passes through each data point and has zero uncertainty at these
        points.

    --- Attributes ---
    bounds : array ({number_of_hyperparameters} x 2)
        The bounds for the hyperparameters
    Xtdict : dict
        dictionary of sampled points
    Xt : array
        array of all sampled points ({number_of_samples} x {number_of_hyperparameters})
    Yt : array
        accuracy of the ml model at each iteration
    --- Methods ---
    objF :
        returns the accuracy/score of the MLmodel at each iteration using MLmodel.score() or scoring_function()
    hyperparameter_convergence_plots :
        plots convergence plots for each hyperparameter
    """

    def __init__(self,
                 hps,
                 MLmodel,
                 NpI = None,
                 optim_rout = 'minimize',
                 using_own_score = False,
                 **kwargs):

        for key, value in kwargs.items():
            setattr(self, key, value)

        # Get hyperparameter info and convert to hyperparameter class
        self.hps = {}
        self.Ncontinous_hps = 0
        for hp in hps:
            self.hps[hp] = hyperparam(hps[hp])
            # Count number of continuous hyperparameters
            if self.hps[hp].kind == 'continuous':
                self.Ncontinous_hps += 1
        self.continous_hps = [hp for hp in self.hps if self.hps[hp].kind == 'continuous']

        # Objective function to minimise
        self.MLmodel = MLmodel

        # Number of hyperparameters
        self.N_hps = len(self.hps.keys())

        # --- Initial sample data
        if NpI is None:
            self.NpI = 2 ** self.N_hps
        else:
            self.NpI = NpI

            
        # --- Optimisation routine for the acquisition function
        self.optim_rout = optim_rout
        # Now define a new dictionary for use in discrete MCMC optimisation
        if self.optim_rout == 'MCMC-discrete':
            self.x_dict = {}
            for i, hp in enumerate(self.hps.keys()):
                self.x_dict[i] = list(self.hps[hp].vals)
                print(self.x_dict[i])

            
        # Get training data
        self.X_train = kwargs['X_train']
        self.y_train = kwargs['y_train']

        # Establish a dictionary for our hyperparameter values that we sample
        self.Xtdict = {}
        # ...and then an array for the same thing but with each column being
        # a different hyperparameter and ordered alphabetically
        self.Xt = np.zeros((self.NpI, len(self.hps.keys())))
        # We also need to collect together all of the bounds for the optimization routing into one array
        self.bounds = np.zeros((len(self.hps.keys()), 2))

        # Get some initial samples on the unit interval
        Xt = lhs(len(self.hps.keys()), samples=self.NpI, criterion='centermaximin')

        # For each hyper parameter, rescale the unit inverval on the 
        # appropriate range for that hp and store in a dict
        for i, hp in enumerate(sorted(self.hps.keys())):
            self.Xtdict[hp] = self.hps[hp].bounds[0] + Xt[:, i] * (self.hps[hp].bounds[1] - self.hps[hp].bounds[0])
            # convert these to an int if kind = 'discrete'
            
            if self.hps[hp].kind == 'discrete':
                self.Xtdict[hp] = self.Xtdict[hp].astype(int)

            self.bounds[i, :] = self.hps[hp].bounds

            self.Xt[:, i] = self.Xtdict[hp]

        # Have we passed in our own score function or are we using the method attached to
        # the MLmodel.score()
        self.using_own_score = using_own_score
        if self.using_own_score:
            self.score = kwargs['scoring_function']


        # Calculate objective function at the sampled points
        self.Yt = self.objF(pars=self.Xtdict, n=self.NpI)

        # --- Number of iterations
        if 'Niter' in kwargs.keys():
            self.Niter = kwargs['Niter']
        else:
            self.Niter = 10 * self.N_hps
        logging.info('Will perform {} iterations'.format(self.Niter))

        # --- Number of optimisations of the acquisition function
        if 'n_restarts' in kwargs.keys():
            self.n_restarts = kwargs['n_restarts']
        else:
            self.n_restarts = 25 * self.N_hps

        # --- Optimisation method used
        if 'method' in kwargs.keys():
            self.method = kwargs['method']
        else:
            self.method = 'L-BFGS-B'

        # --- Define the Gaussian mixture model
        if 'kernel' in kwargs.keys():
            self.kernel = kwargs['kernel']
        else:
            self.kernel = RBF()

        if 'noise' in kwargs.keys():
            self.noise = kwargs['noise']
        else:
            self.noise = 0.1

        self.gpr = GaussianProcessRegressor(kernel=self.kernel, alpha=self.noise * 2)




    def optimise(self):
        for i in range(self.Niter):
            logging.info('Iteration {}'.format(i))
            it1 = iteration(self)
            self.Xt = it1.Xt
            self.Yt = it1.Yt
            print('current accuracy:', self.Yt[-1])
            print('best accuracy:', max(self.Yt))
            self.gpr.fit(self.Xt, self.Yt)

        # Print out best result
        max_val = max(self.Yt)
        best_params_vals = self.Xt[np.where(self.Yt == max_val)[0][0]]
        logging.info('Best result {}: Params: {}'.format(max_val, best_params_vals))
        best_params = {}
        for key, val in zip(self.MLmodel.get_params(), best_params_vals):
            best_params[key] = val
        logging.info('Best result {}: Params: {}'.format(max_val, best_params))
        return self

    def objF(self, pars, **kwargs):

        # Number of hyperparameter values to try.
        n = 1
        if 'n' in kwargs.keys():
            n = kwargs['n']

        # Initiate array to accumate the accuracy of the model
        sc = np.zeros(n)

        # Establish the basic ML model
        model = self.MLmodel


        for i in range(n):

            # Get dictionary of hyperparameter values to test at the ith iteration
            hps_iter = {}
            for hp in pars.keys():
                if self.hps[hp].kind == 'discrete':
                    hps_iter[hp] = int(pars[hp][i])
                else:
                    hps_iter[hp] = pars[hp][i]

            # Create instance of MLmodel with the hps at this iteration
            model.set_params(**hps_iter)

            # Train
            model.fit(self.X_train, self.y_train)

            # Score
            if self.using_own_score:
                sc[i] = self.score(self.X_train, self.y_train)
            else:
                sc[i] = np.mean(cross_val_score(model, self.X_train, self.y_train, cv=5))

            print(hps_iter, f"score: {sc[i]}")

        return sc

    def hyperparameter_convergence_plots(self):
        """
        Plot convergence plots for each hyperparameter
        """

        rcParams['font.size'] = 16
        rcParams['font.family'] = 'serif'
        rcParams['legend.frameon'] = False
        rcParams['text.color'] = 'grey'
        rcParams['xtick.color'] = 'grey'
        rcParams['ytick.color'] = 'grey'
        rcParams['xtick.major.width'] = 2
        rcParams['ytick.major.width'] = 2
        rcParams['axes.labelcolor'] = 'grey'

        Ncols = 2
        Nrows = np.floor(self.N_hps / Ncols) + 1

        fig, ax = plt.subplots(figsize=(16, 5 * Nrows))
        plt.subplots_adjust(wspace=0.2, hspace=0.4)
        for hpi, hp in enumerate(sorted(self.hps)):
            plt.subplot(Nrows, Ncols, hpi + 1)
            plt.plot(self.Xt[:, hpi], '.', markersize=15, color='silver')
            plt.xlim()
            plt.xlabel('Iteration')
            plt.title(hp, y=1.03)
            ax.grid(which='major', axis='x')
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['bottom'].set_visible(False)
            ax.spines['left'].set_visible(False)

        plt.show()