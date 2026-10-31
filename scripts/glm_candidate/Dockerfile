ARG BASE_IMAGE=nvcr.io/nvidia/pytorch@sha256:2140e699b3beaf7f96a0081fd9c9406bc3832b435cdb60dfa2d261f7d2f34a1c
FROM ${BASE_IMAGE}
ARG TF_COMMIT
COPY h100/constraints.txt /opt/h100/constraints.txt
RUN pip install --no-cache-dir -c /opt/h100/constraints.txt \
      "git+https://github.com/ashhart/TensorFold.git@${TF_COMMIT}" \
      av==18.1.0 xgrammar==0.2.8 && tensorfold --version
COPY patches /opt/tf-patches
COPY h100/apply_patches.py /opt/h100/apply_patches.py
RUN python -B /opt/h100/apply_patches.py
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
