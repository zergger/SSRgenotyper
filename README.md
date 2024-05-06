# Modified SSRgenotyper Documentation

## Overview
This document serves as a guide for using the modified version of the SSRgenotyper, which is designed to genotype Short Tandem Repeats (STRs) using pre-identified SSR information. Unlike the original version available at [dlewis27/SSRgenotyper](https://github.com/dlewis27/SSRgenotyper), this modified version does not include the built-in SSR identification algorithm. Instead, it utilizes SSR information directly provided in the input files, which should be prepared using the MISA tool for SSR mining.

## Modifications
The key modifications in this version are as follows:
- **Removal of Built-in SSR Identification Algorithm**: The built-in algorithm for SSR identification has been removed. Instead, this version directly utilizes SSR information mined by MISA, which should be pre-written in the input files. By reading this SSR information from the input files, the tool performs genotyping directly.
- **Addition of Jupyter Notebooks**: Two Jupyter notebooks have been added for convenience. These notebooks are designed for personal use and may not be universally applicable:
  - **SNPvcf2gpop**: This notebook is designed to convert SNP data from VCF format to GenePop format.
  - **STRvcf2gpop**: This notebook facilitates the conversion of VCF files obtained from [lobSTR](https://github.com/mgymrek/lobstr-code) to GenePop format.

## Note
The additional Jupyter notebooks are primarily for personal use and are not guaranteed to work in all environments or setups. Users are encouraged to modify and adapt the notebooks according to their specific requirements.

## Configuration and Options
For detailed configuration options and additional command-line arguments, refer to the original documentation of SSRgenotyper, as the fundamental operation remains similar, excluding the SSR identification phase.

