#!/bin/bash

UNIGEN=~/sat-tools/unigen-bin/unigen
SAMPLES=5
PW=2
W=20
H=20

benchmarks=(
"Chess"
"Simple Wall"
"Rooms"
"Paths"
"Simple Knot"
"Trick Knot"
"Red Maze"
"Platformer"
)

mkdir -p unigen_gallery

for name in "${benchmarks[@]}"
do
    safe=$(echo "$name" | sed 's/ /_/g')

    echo
    echo "==============================="
    echo "$name"
    echo "==============================="

    $UNIGEN \
        --samples $SAMPLES \
        --sampleout unigen_gallery/${safe}_samples.txt \
        sat_width_gallery_out/${safe}_pw${PW}_plain.cnf

    python3 decode_unigen_samples.py \
        "$name" \
        $W $H $PW \
        unigen_gallery/${safe}_samples.txt \
        unigen_gallery/${safe}
done

echo
echo "Finished UniGen gallery."
