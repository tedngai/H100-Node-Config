ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ARG TF_COMMIT
COPY h100/constraints.txt /opt/h100/constraints.txt
RUN pip install --no-cache-dir -c /opt/h100/constraints.txt \
      "git+https://github.com/ashhart/TensorFold.git@${TF_COMMIT}" \
      av==18.1.0 xgrammar==0.2.8 && tensorfold --version
COPY patches /opt/tf-patches
RUN cd "$(python -B -c 'import importlib.util,pathlib; print(pathlib.Path(next(iter(importlib.util.find_spec("tensorfold").submodule_search_locations))).parent)')" && \
    for p in /opt/tf-patches/*.patch; do patch --batch --fuzz=0 -p0 --forward < "$p" || exit 1; done
COPY h100/device_patch.py /opt/h100/device_patch.py
RUN python -B /opt/h100/device_patch.py && \
    python -B -c 'import tensorfold.cuda.server, tensorfold.families.glm5_next.cuda.engine, tensorfold.vision.glm, av, xgrammar'
COPY tools /opt/recipe-tools
COPY h100/entrypoint.sh /opt/h100/entrypoint.sh
RUN chmod 755 /opt/h100/entrypoint.sh && bash -n /opt/h100/entrypoint.sh
ARG RECIPE_COMMIT
ARG PATCHES_HASH
LABEL tf.patches=${PATCHES_HASH} h100.recipe.commit=${RECIPE_COMMIT} h100.tensorfold.commit=${TF_COMMIT}
ENV HF_HOME=/root/.cache/huggingface TORCH_EXTENSIONS_DIR=/cache/torch_extensions TRITON_CACHE_DIR=/cache/triton
WORKDIR /workspace
ENTRYPOINT ["/opt/h100/entrypoint.sh"]
