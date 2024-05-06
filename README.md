# Modified SSRgenotyper Documentation

## Overview
This document serves as a guide for using the modified version of the SSRgenotyper, which is designed to genotype Short Tandem Repeats (STRs) using pre-identified SSR information. Unlike the original version available at [dlewis27/SSRgenotyper](https://github.com/dlewis27/SSRgenotyper), this modified version does not include the built-in SSR identification algorithm. Instead, it utilizes SSR information directly provided in the input files, which should be prepared using the MISA tool for SSR mining.

## Modifications
The key modification in this version of SSRgenotyper is the removal of the internal SSR recognition algorithm. The tool now relies on external SSR information, which needs to be specified in the input files. This approach is intended to streamline the genotyping process by directly leveraging SSR data mined using MISA or similar tools.

## Configuration and Options
For detailed configuration options and additional command-line arguments, refer to the original documentation of SSRgenotyper, as the fundamental operation remains similar, excluding the SSR identification phase.

