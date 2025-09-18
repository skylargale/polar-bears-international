#!/bin/bash -l
#PBS -N seaice_metrics
#PBS -A UWAS0072
#PBS -q casper
#PBS -l select=1:ncpus=16:ngpus=1:mem=64GB
#PBS -l walltime=24:00:00
#PBS -j oe
#PBS -m abe
#PBS -o seaice_metrics.out

export SRCDIR=.

module purge

/glade/u/home/skygale/hudson_env/bin/python $SRCDIR/run_calc_metrics.py
