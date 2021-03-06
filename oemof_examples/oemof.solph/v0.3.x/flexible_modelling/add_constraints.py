# -*- coding: utf-8 -*-
"""
General description
-------------------
This script shows how to add an individual constraint to the oemof solph
OperationalModel.
The constraint we add forces a flow to be greater or equal a certain share
of all inflows of its target bus. Moreover we will set an emission constraint.
If you want to model an emission constraint and do not want to get into
the details of creating constraints, there is another example 

https://github.com/oemof/oemof-examples/blob/master/oemof_examples/
oemof.solph/v0.3.x/emission_constraint/emission_constraint.py

that shows how to use the built-in oemof function.

Installation requirements
-------------------------
This example requires the latest version of oemof. Install by:

    pip install oemof

31.10.2016 - simon.hilpert@uni-flensburg.de
25.02.2020 - jann.launer@rl-institut.de
"""
import logging
import pyomo.environ as po
import pandas as pd

from oemof.solph import (Sink, Source, Transformer, Bus, Flow, Model,
                         EnergySystem)

import oemof.outputlib as outputlib


def run_add_constraints_example(solver='cbc', nologg=False):
    if not nologg:
        logging.basicConfig(level=logging.INFO)
    # ##### creating an oemof solph optimization model, nothing special here ##
    # create an energy system object for the oemof solph nodes
    es = EnergySystem(timeindex=pd.date_range('1/1/2017', periods=4, freq='H'))
    # add some nodes

    boil = Bus(label="oil")
    blig = Bus(label="lignite")
    b_el = Bus(label="b_el")

    es.add(boil, blig, b_el)

    oil_source = Source(label="oil source", outputs={boil: Flow()})
    lignite_source = Source(label="lignite source", outputs={blig: Flow()})

    sink = Sink(label="Sink", inputs={
                                b_el: Flow(nominal_value=40,
                                           actual_value=[0.5, 0.4, 0.3, 1],
                                           fixed=True)})
    pp_oil = Transformer(label='pp_oil',
                         inputs={boil: Flow()},
                         outputs={b_el: Flow(nominal_value=50,
                                             variable_costs=25)},
                         conversion_factors={b_el: 0.39})
    pp_lig = Transformer(label='pp_lig',
                         inputs={
                             blig: Flow()},
                         outputs={
                             b_el: Flow(nominal_value=50,
                                        variable_costs=10)},
                         conversion_factors={b_el: 0.41})

    es.add(sink, pp_oil, pp_lig, oil_source, lignite_source)

    # create the model
    om = Model(energysystem=es)

    # add specific emission values to flow objects if source is a commodity bus
    for s, t in om.flows.keys():
        if s is boil:
            om.flows[s, t].emission_factor = 0.27  # t/MWh
        if s is blig:
            om.flows[s, t].emission_factor = 0.39  # t/MWh

    # Increase the emission limit will increase the share of lignite, because
    # lignite is cheaper in this example but has higher specific emissions.
    emission_limit = 75

    # add the outflow share
    om.flows[(boil, pp_oil)].outflow_share = [1, 0.5, 0, 0.3]

    # Now we are going to add a 'sub-model' and add a user specific constraint
    # first we add a pyomo Block() instance that we can use to add our
    # constraints. Then, we add this Block to our previous defined
    # Model instance and add the constraints.
    myblock = po.Block()

    # create a pyomo set with the flows (i.e. list of tuples),
    # there will of course be only one flow inside this set, the one we used to
    # add outflow_share
    myblock.MYFLOWS = po.Set(initialize=[k for (k, v) in om.flows.items()
                                         if hasattr(v, 'outflow_share')])

    # pyomo does not need a po.Set, we can use a simple list as well
    myblock.COMMODITYFLOWS = [k for (k, v) in om.flows.items()
                              if hasattr(v, 'emission_factor')]

    # add the sub-model to the oemof Model instance
    om.add_component('MyBlock', myblock)

    def _inflow_share_rule(m, s, e, t):
        """pyomo rule definition: Here we can use all objects from the block or
        the om object, in this case we don't need anything from the block
        except the newly defined set MYFLOWS.
        """
        expr = (om.flow[s, e, t] >= om.flows[s, e].outflow_share[t] *
                sum(om.flow[i, o, t] for (i, o) in om.FLOWS if o == e))
        return expr

    myblock.inflow_share = po.Constraint(myblock.MYFLOWS, om.TIMESTEPS,
                                         rule=_inflow_share_rule)
    # add emission constraint
    myblock.emission_constr = po.Constraint(expr=(
            sum(om.flow[i, o, t] *
                om.flows[i, o].emission_factor
                for (i, o) in myblock.COMMODITYFLOWS
                for t in om.TIMESTEPS) <= emission_limit))

    # solve and write results to dictionary
    # you may print the model with om.pprint()
    om.solve(solver=solver)
    logging.info("Successfully finished.")

    # print the resulting emissions to verify
    results = outputlib.processing.results(om)

    emitted = {}
    for k, v in results.items():
        if k[0] == boil:
            emitted['oil'] = (
                    v['sequences']['flow'].sum() * om.flows[k].emission_factor)
        if k[0] == blig:
            emitted['lignite'] = (
                    v['sequences']['flow'].sum() * om.flows[k].emission_factor)

    print('emissions through oil consumption \n', emitted['oil'])
    print('emissions through lignite consumption \n', emitted['lignite'])
    print('total emissions \n', sum(emitted.values()))


if __name__ == "__main__":
    run_add_constraints_example()
